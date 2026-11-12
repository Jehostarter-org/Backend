import hmac
import hashlib
import json
import logging
import time
from decimal import Decimal
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.views import APIView

from .models import MembershipPlan, UserMembership
from shops.models import BoostRequest, ShopListing, Order, InstallmentSchedule
from services.models import ServiceRequest

logger = logging.getLogger("backend.internal_payments")


def verify_hmac(
    payload_bytes: bytes,
    signature_header: str,
    secret: str,
    tolerance: int = 300,
) -> bool:
    """
    Verify an inbound HMAC-SHA256 signature with replay-attack protection.
    Header format: t={timestamp},v1={hex_digest}
    Payload is computed as: {timestamp}.{payload_bytes}
    """
    if not signature_header or not secret:
        return False

    parts = dict(item.split("=", 1) for item in signature_header.split(",") if "=" in item)
    timestamp_str = parts.get("t")
    expected_v1 = parts.get("v1")

    if not timestamp_str or not expected_v1:
        return False

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False

    current_time = int(time.time())
    if abs(current_time - timestamp) > tolerance:
        logger.warning(
            f"HMAC timestamp rejected: clock drift ({abs(current_time - timestamp)}s) exceeds tolerance ({tolerance}s)"
        )
        return False

    signed_payload = f"{timestamp_str}.".encode("utf-8") + payload_bytes
    computed_sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=signed_payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_sig, expected_v1)


class InternalPaymentCallbackView(APIView):
    """
    Private endpoint called exclusively by the Payment Microservice
    upon receiving verified payment events (e.g. Stripe webhook confirmation, checkout completion).
    Protected by shared secret token and HMAC-SHA256 cryptographic signature.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # Bypass standard Django user session / JWT auth

    def post(self, request, *args, **kwargs):
        # 1. Verify service token
        service_token = request.headers.get("X-Service-Token")
        expected_secret = getattr(
            settings,
            "PAYMENT_SERVICE_TOKEN",
            getattr(settings, "INTERNAL_SERVICE_SECRET", ""),
        )

        if not service_token or not hmac.compare_digest(service_token, expected_secret):
            logger.warning("Rejected callback: Invalid or missing X-Service-Token")
            return JsonResponse({"detail": "Invalid or missing service token."}, status=403)

        # 2. Verify HMAC cryptographic signature
        signature_header = request.headers.get("X-Service-Signature")
        raw_body = request.body

        if not verify_hmac(raw_body, signature_header, expected_secret):
            logger.warning("Rejected callback: Invalid or expired HMAC signature")
            return JsonResponse({"detail": "Invalid or expired signature header."}, status=401)

        # 3. Parse and process payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Malformed JSON in payment callback: {e}")
            return JsonResponse({"detail": "Malformed JSON payload."}, status=400)

        event = payload.get("event")
        payment_id = payload.get("payment_id")
        user_id = payload.get("user_id")
        resource_type = payload.get("resource_type")
        resource_id = payload.get("resource_id")
        amount = payload.get("amount")
        currency = payload.get("currency")
        provider = payload.get("provider", "stripe")
        provider_tx_id = payload.get("provider_transaction_id", "")

        logger.info(
            f"Processing payment callback: event={event}, payment_id={payment_id}, "
            f"user_id={user_id}, resource={resource_type}:{resource_id}"
        )

        User = get_user_model()

        # 4. Handle events
        if event == "payment.authorized":
            if resource_type == "service_request":
                sr = ServiceRequest.objects.filter(id=resource_id).first() or ServiceRequest.objects.filter(payment_id=payment_id).first()
                if sr:
                    sr.payment_status = 'authorized'
                    sr.payment_id = payment_id
                    sr.save()
                    logger.info(f"ServiceRequest {sr.id} payment hold authorized ({payment_id})")
            elif resource_type in ("order", "installment"):
                inst = InstallmentSchedule.objects.filter(id=resource_id).first() or InstallmentSchedule.objects.filter(payment_id=payment_id).first()
                if inst:
                    inst.status = 'authorized'
                    inst.payment_id = payment_id
                    inst.save()
                    logger.info(f"InstallmentSchedule {inst.id} payment hold authorized ({payment_id})")

        elif event in ("payment.paid", "payment.captured"):
            if resource_type == "membership":
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    logger.error(f"Callback user_id {user_id} not found in database")
                    return JsonResponse({"detail": "User not found."}, status=404)

                plan_name = resource_id  # e.g. "gold" or "silver"
                country = user.current_country or "AU"
                plan = MembershipPlan.objects.filter(plan=plan_name, country_code=country).first()
                if not plan:
                    plan = MembershipPlan.objects.filter(plan=plan_name).first()
                duration = plan.duration_days if plan else 30

                # Deactivate previous active memberships
                user.memberships.filter(is_active=True).update(is_active=False)

                # Create new active membership
                membership = UserMembership.objects.create(
                    user=user,
                    plan=plan_name,
                    country_code=country,
                    started_at=timezone.now(),
                    expires_at=timezone.now() + timedelta(days=duration),
                    is_active=True,
                    payment_reference=payment_id,
                    payment_gateway=provider,
                    amount_paid=Decimal(str(amount)) if amount is not None else None,
                    currency_paid=currency or "USD",
                )
                logger.info(f"Activated {plan_name} membership for user {user.id}")

            elif resource_type == "boost":
                boost = BoostRequest.objects.filter(id=resource_id).first()
                if not boost:
                    boost = BoostRequest.objects.filter(payment_reference=payment_id).first()

                if boost:
                    boost.approved = True
                    boost.approved_at = timezone.now()
                    if amount is not None:
                        boost.amount_paid = Decimal(str(amount))
                    boost.save()

                    listing = boost.listing
                    listing.is_boosted = True
                    listing.boost_expires_at = timezone.now() + timedelta(days=boost.duration_days)
                    listing.save()
                    logger.info(f"Approved boost {boost.id} for listing {listing.id}")
                else:
                    logger.warning(f"Boost request {resource_id} not found for payment {payment_id}")

            elif resource_type == "service_request":
                sr = ServiceRequest.objects.filter(id=resource_id).first() or ServiceRequest.objects.filter(payment_id=payment_id).first()
                if sr:
                    sr.payment_status = 'captured'
                    if amount is not None:
                        sr.price = Decimal(str(amount))
                    sr.save()
                    logger.info(f"ServiceRequest {sr.id} payment captured for {amount} {currency}")

            elif resource_type in ("order", "installment"):
                inst = InstallmentSchedule.objects.filter(id=resource_id).first() or InstallmentSchedule.objects.filter(payment_id=payment_id).first()
                if inst:
                    inst.status = 'paid'
                    inst.paid_at = timezone.now()
                    inst.save()
                    order = inst.order
                    if order.status == 'approved':
                        order.status = 'in_fulfillment'
                        order.save()
                    logger.info(f"InstallmentSchedule {inst.id} marked as paid ({payment_id})")

        elif event in ("payment.released", "payment.canceled"):
            if resource_type == "service_request":
                sr = ServiceRequest.objects.filter(id=resource_id).first() or ServiceRequest.objects.filter(payment_id=payment_id).first()
                if sr:
                    sr.payment_status = 'released'
                    sr.status = 'cancelled'
                    sr.save()
                    logger.info(f"ServiceRequest {sr.id} payment hold released and cancelled")
            elif resource_type in ("order", "installment"):
                inst = InstallmentSchedule.objects.filter(id=resource_id).first() or InstallmentSchedule.objects.filter(payment_id=payment_id).first()
                if inst:
                    inst.status = 'refunded'
                    inst.save()
                    order = inst.order
                    order.status = 'cancelled'
                    order.save()
                    logger.info(f"Order {order.id} installment hold released")

        elif event == "payment.refunded":
            if resource_type == "membership":
                UserMembership.objects.filter(payment_reference=payment_id).update(is_active=False)
                logger.info(f"Deactivated membership for refunded payment {payment_id}")
            elif resource_type == "boost":
                boost = BoostRequest.objects.filter(payment_reference=payment_id).first()
                if boost:
                    boost.approved = False
                    boost.save()
                    listing = boost.listing
                    listing.is_boosted = False
                    listing.save()
                    logger.info(f"Revoked boost for refunded payment {payment_id}")
            elif resource_type == "service_request":
                sr = ServiceRequest.objects.filter(payment_id=payment_id).first()
                if sr:
                    sr.payment_status = 'refunded'
                    sr.save()
                    logger.info(f"ServiceRequest {sr.id} marked as refunded")
            elif resource_type in ("order", "installment"):
                inst = InstallmentSchedule.objects.filter(payment_id=payment_id).first()
                if inst:
                    inst.status = 'refunded'
                    inst.save()
                    logger.info(f"InstallmentSchedule {inst.id} marked as refunded")

        elif event == "payment.transferred":
            logger.info(f"Provider payout transfer completed for payment {payment_id}")

        return JsonResponse({"status": "success", "event": event, "payment_id": payment_id})
