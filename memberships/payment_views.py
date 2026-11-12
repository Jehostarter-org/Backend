import logging
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MembershipPlan, UserMembership
from .serializers import UserMembershipSerializer
from utils.payment_client import PaymentServiceClient, PaymentClientError

logger = logging.getLogger("backend.payments")


class InitializePaymentView(APIView):
    """
    Endpoint matching frontend RTK Query /api/payments/initialize.
    Initializes a Stripe Checkout session via the Payment Microservice.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data
        plan_name = data.get("plan", "gold")
        country = user.current_country or "AU"

        currency = getattr(settings, 'COUNTRY_CURRENCY_MAP', {}).get(country, 'USD')
        default_price = Decimal("25.00") if plan_name == "gold" else Decimal("10.00")
        if currency == "NGN":
            default_price = Decimal("35000.00") if plan_name == "gold" else Decimal("15000.00")

        plan = MembershipPlan.objects.filter(plan=plan_name, country_code=country).first()
        if not plan:
            plan = MembershipPlan.objects.filter(plan=plan_name).first()
        if not plan:
            plan, _ = MembershipPlan.objects.get_or_create(
                plan=plan_name,
                country_code=country,
                defaults={
                    "price": default_price,
                    "currency": currency,
                    "duration_days": 30,
                    "can_create_shop": True,
                    "can_create_community": True,
                    "can_join_community": True,
                    "can_boost_products": True,
                    "can_request_home_inspection": True,
                    "can_use_airport_pickup": True,
                    "can_use_chaperon": True,
                    "max_shop_listings": 50,
                },
            )

        frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        # The frontend page that confirms a payment lives at this path. The frontend's
        # own `callback_url` (e.g. /payment/verify) points to a page that does not exist,
        # and trusting a client-supplied redirect is unsafe, so always build it from FRONTEND_URL.
        callback_url = f"{frontend_base}/customer-details/payment/verify"
        success_url = f"{callback_url}?reference={{CHECKOUT_SESSION_ID}}&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = data.get("cancel_url") or f"{frontend_base}/customer-details/packages"

        idempotency_key = f"init_{plan_name}_{user.id}_{int(timezone.now().timestamp())}"

        client = PaymentServiceClient()
        try:
            payment = client.create_payment(
                user_id=user.id,
                amount=plan.price,
                currency=plan.currency,
                purpose=f"membership_upgrade_{plan_name}",
                resource_type="membership",
                resource_id=plan_name,
                idempotency_key=idempotency_key,
                metadata={
                    "user_email": user.email,
                    "country": country,
                },
            )
            payment_id = payment.get("id")
            initiate_res = client.initiate_payment(
                payment_id=payment_id,
                provider="stripe",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=user.email,
            )

            checkout_url = initiate_res.get("checkout_url")
            session_id = initiate_res.get("session_id")

            return Response(
                {
                    "status": "success",
                    "checkout_url": checkout_url,
                    "authorization_url": checkout_url,  # For Paystack/Stripe frontend compatibility
                    "reference": session_id or payment_id,
                    "payment_id": payment_id,
                    "session_id": session_id,
                    "data": {
                        "authorization_url": checkout_url,
                        "reference": session_id or payment_id,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except PaymentClientError as e:
            logger.error(f"PaymentClientError during payment initialization: {e}")
            return Response(
                {"detail": "Payment could not be started. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as e:
            logger.error(f"Unexpected error during payment initialization: {e}")
            return Response(
                {"detail": "Unable to communicate with payment gateway."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class VerifyPaymentStatusView(APIView):
    """
    Endpoint matching frontend RTK Query GET /api/payments/verify/:reference.
    Verifies payment completion and ensures membership is active.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, reference):
        user = request.user

        # 1. Check if user already has active membership with this reference or active gold
        active_mem = user.memberships.filter(is_active=True).first()
        if active_mem and (active_mem.payment_reference == reference or active_mem.plan == "gold"):
            return Response(
                {
                    "status": "success",
                    "reference": reference,
                    "membership": UserMembershipSerializer(active_mem).data,
                    "message": "Payment verified and membership active.",
                },
                status=status.HTTP_200_OK,
            )

        # 2. Query payment_service to check status
        client = PaymentServiceClient()
        try:
            payment_info = client.get_payment(reference)
            payment_status = payment_info.get("status")

            if payment_status == "paid":
                # Ensure local membership is created/activated
                plan_name = payment_info.get("resource_id", "gold")
                country = user.current_country or "AU"
                plan = MembershipPlan.objects.filter(plan=plan_name, country_code=country).first()
                if not plan:
                    plan = MembershipPlan.objects.filter(plan=plan_name).first()
                duration = plan.duration_days if plan else 30

                user.memberships.filter(is_active=True).update(is_active=False)
                new_membership = UserMembership.objects.create(
                    user=user,
                    plan=plan_name,
                    country_code=country,
                    started_at=timezone.now(),
                    expires_at=timezone.now() + timedelta(days=duration),
                    is_active=True,
                    payment_reference=reference,
                    payment_gateway=payment_info.get("provider", "stripe"),
                    amount_paid=Decimal(str(payment_info.get("amount", plan.price if plan else 0))),
                    currency_paid=payment_info.get("currency", "USD"),
                )

                return Response(
                    {
                        "status": "success",
                        "reference": reference,
                        "membership": UserMembershipSerializer(new_membership).data,
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(
                {
                    "status": payment_status or "pending",
                    "reference": reference,
                    "message": f"Payment is {payment_status}",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.warning(f"Error checking payment {reference} with microservice: {e}")
            # If webhook already activated it in the background:
            if active_mem:
                return Response(
                    {
                        "status": "success",
                        "reference": reference,
                        "membership": UserMembershipSerializer(active_mem).data,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"status": "failed", "detail": "Payment verification failed or pending."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class VerifyGoldPlanPaymentView(APIView):
    """
    Endpoint matching frontend RTK Query POST /api/plan/verify/gold/plan/payment.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        reference = request.data.get("reference") or request.data.get("paymentReference")

        if reference:
            view = VerifyPaymentStatusView()
            return view.get(request, reference)

        active = user.memberships.filter(is_active=True, plan="gold").first()
        if active:
            return Response({"status": "success", "membership": UserMembershipSerializer(active).data})

        return Response({"status": "failed", "detail": "Missing payment reference"}, status=400)
