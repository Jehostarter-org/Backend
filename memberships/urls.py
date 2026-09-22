from django.urls import path
from .views import (
    CheckEligibilityExistsView,
    CheckGoldEligibilityDestinationView,
    CheckGoldEligibilityHomeView,
    MembershipPlanListView,
    MyMembershipView,
    UpgradeMembershipView,
    AdminEligibilityListAllView,
    AdminEligibilityDetailView,
    AdminProcessEligibilityView,
    AdminEligibilityStatsView,
)

urlpatterns = [
    path('plans/', MembershipPlanListView.as_view(), name='membership_plans'),
    path('my/', MyMembershipView.as_view(), name='my_membership'),
    path('upgrade/', UpgradeMembershipView.as_view(), name='upgrade_membership'),
    path('plan/gold/eligibility/check/destination', CheckGoldEligibilityDestinationView.as_view(), name='gold_eligibility_destination'),
    path('plan/gold/eligibility/check/home', CheckGoldEligibilityHomeView.as_view(), name='gold_eligibility_home'),
    path('plan/gold/eligibility/exists', CheckEligibilityExistsView.as_view(), name='eligibility_exists'),

    # ── Admin: Gold eligibility submission review ─────────────────────────
    path('admin/eligibility/', AdminEligibilityListAllView.as_view(), name='admin_eligibility_list'),
    path('admin/eligibility/stats/', AdminEligibilityStatsView.as_view(), name='admin_eligibility_stats'),
    path('admin/eligibility/<str:pk>/', AdminEligibilityDetailView.as_view(), name='admin_eligibility_detail'),
    path('admin/eligibility/<str:pk>/process/', AdminProcessEligibilityView.as_view(), name='admin_process_eligibility'),
] 
