from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta
from .models import MembershipPlan, UserMembership
from .serializers import MembershipPlanSerializer, UserMembershipSerializer, UpgradeMembershipSerializer


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
