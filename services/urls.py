from django.urls import path
from .views import (
    ServiceRequestListCreateView,
    ServiceRequestDetailView,
    AvailableServicesView,
    ClaimServiceView,
    MyProviderJobsView,
    UpcomingPickupsView,
    InspectionReportUploadView,
    ReviewServiceView,
    ServiceProviderProfileListCreateView,
    ServiceProviderProfileDetailView,
    MigrationSpecialistApplyView,
    MigrationSpecialistApplicationStatusView,
)

urlpatterns = [
    # ── Service Requests ──────────────────────────────────────────────────────
    path('', ServiceRequestListCreateView.as_view(), name='service_list_create'),

    # ── Provider Dashboard ────────────────────────────────────────────────────
    path('available/', AvailableServicesView.as_view(), name='available_services'),
    path('my-jobs/', MyProviderJobsView.as_view(), name='my_provider_jobs'),
    path('upcoming-pickups/', UpcomingPickupsView.as_view(), name='upcoming_pickups'),

    # ── File Uploads ──────────────────────────────────────────────────────────
    path('<str:pk>/upload-report/', InspectionReportUploadView.as_view(), name='upload_report'),

    # ── Reviews ───────────────────────────────────────────────────────────────
    path('<str:pk>/review/', ReviewServiceView.as_view(), name='review_service'),

    # ── Provider Registration ─────────────────────────────────────────────────
    path('provider-profiles/', ServiceProviderProfileListCreateView.as_view(), name='provider_profiles'),
    path('provider-profiles/<str:pk>/', ServiceProviderProfileDetailView.as_view(), name='provider_profile_detail'),

    # ── Migration Specialist ──────────────────────────────────────────────────
    path('specialist/apply/', MigrationSpecialistApplyView.as_view(), name='specialist_apply'),
    path('specialist/my-application/', MigrationSpecialistApplicationStatusView.as_view(), name='specialist_application_status'),

    # Dynamic routes must come last so static dashboard routes are not treated as IDs.
    path('<str:pk>/claim/', ClaimServiceView.as_view(), name='claim_service'),
    path('<str:pk>/', ServiceRequestDetailView.as_view(), name='service_detail'),
]
