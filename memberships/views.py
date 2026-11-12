import json
import logging
from datetime import timedelta

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import EligibilityCheck, EligibilityDocument, MembershipPlan, UserMembership
from .serializers import (
    AdminEligibilityDetailSerializer,
    AdminEligibilityListSerializer,
    EligibilityCheckSerializer,
    MembershipPlanSerializer,
    UpgradeMembershipSerializer,
    UserMembershipSerializer,
)

logger = logging.getLogger(__name__)


class MembershipPlanListView(generics.ListAPIView):
    serializer_class = MembershipPlanSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        country = self.request.query_params.get('country', '')
        qs = MembershipPlan.objects.all()
        if country:
            qs = qs.filter(country_code=country)
        return qs


class MyMembershipView(generics.RetrieveAPIView):
    serializer_class = UserMembershipSerializer

    def get_object(self):
        return self.request.user.memberships.filter(is_active=True).first()


class UpgradeMembershipView(APIView):
    def post(self, request):
        serializer = UpgradeMembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        plan_name = serializer.validated_data['plan']
        country   = user.current_country or 'AU'
        from decimal import Decimal
        from django.conf import settings

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

        payment_reference = (
            request.data.get('payment_reference')
            or request.data.get('paymentReference')
            or serializer.validated_data.get('payment_reference', '')
        ).strip()

        # If payment_reference is passed, handle verification / completion
        if payment_reference:
            existing = user.memberships.filter(is_active=True, payment_reference=payment_reference).first()
            if existing:
                return Response(UserMembershipSerializer(existing).data, status=status.HTTP_200_OK)

            from utils.payment_client import PaymentServiceClient
            client = PaymentServiceClient()
            try:
                payment_info = client.get_payment(payment_reference)
                if payment_info.get("status") == "paid":
                    user.memberships.filter(is_active=True).update(is_active=False)
                    membership = UserMembership.objects.create(
                        user=user, plan=plan_name, country_code=country,
                        expires_at=timezone.now() + timedelta(days=plan.duration_days),
                        payment_reference=payment_reference,
                        payment_gateway=payment_info.get("provider", "stripe"),
                        amount_paid=plan.price,
                        currency_paid=plan.currency,
                    )
                    return Response(UserMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)
            except Exception:
                pass  # Fall through to standard checkout initiation

        # Standard Option A: Monolith Orchestration to kick off Stripe Checkout
        from django.conf import settings
        from utils.payment_client import PaymentServiceClient, PaymentClientError

        frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        success_url = serializer.validated_data.get('success_url') or f"{frontend_base}/customer-details/payment/verify?reference={{CHECKOUT_SESSION_ID}}&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = serializer.validated_data.get('cancel_url') or f"{frontend_base}/customer-details/packages"

        idempotency_key = f"upgrade_{plan_name}_{user.id}_{int(timezone.now().timestamp())}"
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

            return Response({
                "checkout_url": checkout_url,
                "authorization_url": checkout_url,  # For frontend backwards-compatibility
                "payment_id": payment_id,
                "session_id": session_id,
                "reference": session_id or payment_id,
                "plan": plan_name,
                "amount": str(plan.price),
                "currency": plan.currency,
                "status": "pending",
            }, status=status.HTTP_200_OK)

        except PaymentClientError as e:
            logger.error("Payment gateway initialization failed: %s", e)
            return Response(
                {"detail": "Payment could not be started. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as e:
            return Response(
                {"detail": "Payment microservice is currently unreachable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


DOCUMENT_FIELD_MAP = {
    'a': {
        'visa_passport_page': {'field': 'visa_document', 'single': True},
        'vevo_check': {'field': 'visa_document', 'single': True},
        'payslip': {'field': 'payslips', 'single': False},
        'bank_statement': {'field': 'bank_statement', 'single': True},
        'address_proof': {'field': 'address_proof', 'single': True},
    },
    'b': {
        'passport': {'field': 'passport', 'single': True},
        'migration_intent': {'field': 'migration_intent', 'single': True},
    },
}


class BaseEligibilityCheckView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    pathway = None  # set in subclass

    def post(self, request):
        user = request.user

        # ── Reject if user already submitted ────────────────────────────────
        if EligibilityCheck.objects.filter(user=user).exists():
            return Response(
                {'detail': 'You have already submitted an eligibility check. Only one submission is allowed.'},
                status=status.HTTP_409_CONFLICT,
            )

        data = request.POST.dict()
        files = request.FILES

        pathway = self.pathway
        metadata = {}

        # Determine document type from upload_type field or infer from pathway
        upload_type = data.get('upload_type', '')

        check = EligibilityCheck.objects.create(
            user=user,
            pathway=pathway,
            status='processing',
            visa_expiry=data.get('visa_expiry') or None,
            passport_expiry=data.get('passport_expiry') or None,
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            destination_country=data.get('destination_country', ''),
            destination_city=data.get('destination_city', ''),
            migration_doc_type=data.get('migration_type', ''),
            metadata=metadata,
        )

        # Save documents from uploaded files
        doc_map = DOCUMENT_FIELD_MAP.get(pathway, {})

        for doc_type, config in doc_map.items():
            field_name = config['field']
            if config['single']:
                file_obj = files.get(field_name)
                if file_obj:
                    EligibilityDocument.objects.create(
                        eligibility_check=check,
                        document_type=doc_type,
                        file=file_obj,
                    )
            else:
                file_list = files.getlist(field_name)
                for f in file_list:
                    EligibilityDocument.objects.create(
                        eligibility_check=check,
                        document_type=doc_type,
                        file=f,
                    )

        # Simple eligibility logic
        check = self._evaluate_eligibility(check)

        return Response(EligibilityCheckSerializer(check).data, status=status.HTTP_201_CREATED)

    def _evaluate_eligibility(self, check):
        documents = list(check.documents.all())
        doc_count = len(documents)

        if doc_count == 0:
            check.status = 'rejected'
            check.save()
            return check

        # Mock verification: accept as approved if at least required docs present
        if check.pathway == 'a' and doc_count >= 4:
            check.status = 'approved'
        elif check.pathway == 'a':
            check.status = 'conditionally_approved'
        elif check.pathway == 'b' and doc_count >= 2:
            check.status = 'conditionally_approved'
        else:
            check.status = 'rejected'

        check.save()
        return check


class CheckEligibilityExistsView(APIView):
    def get(self, request):
        exists = EligibilityCheck.objects.filter(user=request.user).exists()
        return Response({'submitted': exists})


class CheckGoldEligibilityDestinationView(BaseEligibilityCheckView):
    pathway = 'a'


class CheckGoldEligibilityHomeView(BaseEligibilityCheckView):
    pathway = 'b'


class AdminEligibilityListAllView(generics.ListAPIView):
    """Admin: List all gold-eligibility submissions with filters.

    GET /api/plan/admin/eligibility/?status=<status>&pathway=<a|b>
    """
    serializer_class = AdminEligibilityListSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = EligibilityCheck.objects.select_related('user')
        status_filter = self.request.query_params.get('status')
        pathway_filter = self.request.query_params.get('pathway')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if pathway_filter:
            qs = qs.filter(pathway=pathway_filter)
        return qs.order_by('-created_at')


class AdminEligibilityDetailView(generics.RetrieveAPIView):
    """Admin: Full detail of an eligibility submission (incl. documents).

    GET /api/plan/admin/eligibility/<id>/
    """
    serializer_class = AdminEligibilityDetailSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'id'
    lookup_url_kwarg = 'pk'
    queryset = EligibilityCheck.objects.select_related('user').prefetch_related('documents')


class AdminProcessEligibilityView(APIView):
    """Admin: Approve / reject an eligibility submission.

    POST /api/plan/admin/eligibility/<id>/process/
    Body: { action: 'approve' | 'reject', notes?: string }
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        check = get_object_or_404(EligibilityCheck, pk=pk)

        action = request.data.get('action')
        notes = request.data.get('notes', '')

        if action == 'approve':
            check.status = 'approved'
            check.rejection_reason = ''
            check.reviewed_at = timezone.now()
            check.save(update_fields=['status', 'rejection_reason', 'reviewed_at', 'updated_at'])
            return Response({
                'message': f'Eligibility check for {check.user.email or check.user.username} approved.',
                'status': 'approved',
            })

        elif action == 'reject':
            if not notes:
                return Response(
                    {'detail': 'Rejection reason is required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            check.status = 'rejected'
            check.rejection_reason = notes
            check.reviewed_at = timezone.now()
            check.save(update_fields=['status', 'rejection_reason', 'reviewed_at', 'updated_at'])
            return Response({
                'message': f'Eligibility check for {check.user.email or check.user.username} rejected.',
                'status': 'rejected',
                'reason': notes,
            })

        return Response(
            {'detail': 'Invalid action. Use "approve" or "reject".'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class AdminEligibilityStatsView(APIView):
    """Admin: Eligibility submission statistics.

    GET /api/plan/admin/eligibility/stats/
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        def count(**kw):
            return EligibilityCheck.objects.filter(**kw).count()

        return Response({
            'total': count(),
            'pending': count(status='pending'),
            'processing': count(status='processing'),
            'approved': count(status='approved'),
            'conditionally_approved': count(status='conditionally_approved'),
            'rejected': count(status='rejected'),
            'by_pathway': {
                'destination': count(pathway='a'),
                'home': count(pathway='b'),
            },
        })
