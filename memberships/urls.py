from django.urls import path
from .views import MembershipPlanListView, MyMembershipView, UpgradeMembershipView

urlpatterns = [
    path('plans/', MembershipPlanListView.as_view(), name='membership_plans'),
    path('my/', MyMembershipView.as_view(), name='my_membership'),
    path('upgrade/', UpgradeMembershipView.as_view(), name='upgrade_membership'),
] 
