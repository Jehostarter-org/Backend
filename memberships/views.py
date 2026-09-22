import json
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
        country   = user.current_country or 'NG'
        try:
            plan = MembershipPlan.objects.get(plan=plan_name, country_code=country)
        except MembershipPlan.DoesNotExist:
            return Response({'detail': 'Plan not available in your country.'}, status=404)
        user.memberships.filter(is_active=True).update(is_active=False)
        membership = UserMembership.objects.create(
            user=user, plan=plan_name, country_code=country,
            expires_at=timezone.now() + timedelta(days=plan.duration_days),
            payment_reference=serializer.validated_data['payment_reference'],
        )
        return Response(UserMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


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
