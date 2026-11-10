from django.urls import path
from .views import (
    ServiceRequestListCreateView,
    ServiceRequestDetailView,
    DriverServiceRequestDetailView,
    AvailableServicesView,
    ClaimServiceView,
    MyProviderJobsView,
    UpcomingPickupsView,
    InspectionReportUploadView,
    ReviewServiceView,
    RatePassengerView,
    ServiceProviderProfileListCreateView,
    ServiceProviderProfileDetailView,
    MigrationSpecialistApplyView,
    MigrationSpecialistApplicationStatusView,
    AirportListView,
    VehiclePricingView,
    ConfirmVehicleView,
    CalculateDistanceView,
    GeocodeAddressView,
    EstimateDriverArrivalView,
    UpdateDriverLocationView,
    UpdateServiceRequestDistanceView,
    TrackDriverLocationView,
    UpdateTripStatusView,
    BroadcastServiceView,
    PropertyListCreateView,
    PropertyDetailView,
    PublishPropertyView,
    UploadPropertyImageView,
    DeletePropertyImageView,
    PropertySearchView,
    AvailableChaperonesView,
    BroadcastChaperoneServiceView,
    ImmigrationOfficersView,
    AdminProviderPendingApprovalsView,
    AdminProviderAllApprovalsView,
    AdminProviderApprovalDetailView,
    AdminProcessProviderApprovalView,
    AdminProviderStatsView,
    RouteDirectionsView,
    CancelServiceRequestView,
    ServiceRequestPaymentHoldView,
    ProviderStripeConnectOnboardingView,
    ProviderStripeConnectStatusView,
)

urlpatterns = [
    # ── Airport Data ─────────────────────────────────────────────────────────
    path('airports/', AirportListView.as_view(), name='airport_list'),

    # ── Vehicle Pricing (localised per user country) ──────────────────────────
    path('pricing/', VehiclePricingView.as_view(), name='vehicle_pricing'),

    # ── Distance Calculation Endpoints ────────────────────────────────────────
    path('calculate-distance/', CalculateDistanceView.as_view(), name='calculate_distance'),
    path('geocode/', GeocodeAddressView.as_view(), name='geocode_address'),
    path('estimate-driver/', EstimateDriverArrivalView.as_view(), name='estimate_driver'),
    path('update-location/', UpdateDriverLocationView.as_view(), name='update_location'),

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
    path('<str:pk>/rate-passenger/', RatePassengerView.as_view(), name='rate_passenger'),

    # ── Vehicle confirmation (saves server-calculated price onto the request) ─
    path('<str:pk>/confirm-vehicle/', ConfirmVehicleView.as_view(), name='confirm_vehicle'),

    # ── Distance & Trip Management ───────────────────────────────────────────
    path('<str:pk>/update-distance/', UpdateServiceRequestDistanceView.as_view(), name='update_distance'),
    path('<str:pk>/track-driver/', TrackDriverLocationView.as_view(), name='track_driver'),
    path('<str:pk>/trip-status/', UpdateTripStatusView.as_view(), name='trip_status'),
    path('<str:pk>/authorize-hold/', ServiceRequestPaymentHoldView.as_view(), name='service_authorize_hold'),
    path('<str:pk>/cancel/', CancelServiceRequestView.as_view(), name='service_cancel'),

    # ── Provider Registration & Stripe Connect ────────────────────────────────
    path('provider-profiles/stripe-connect/status/', ProviderStripeConnectStatusView.as_view(), name='provider_stripe_connect_status'),
    path('provider-profiles/stripe-connect/', ProviderStripeConnectOnboardingView.as_view(), name='provider_stripe_connect_onboarding'),
    path('provider-profiles/', ServiceProviderProfileListCreateView.as_view(), name='provider_profiles'),
    path('provider-profiles/<str:pk>/', ServiceProviderProfileDetailView.as_view(), name='provider_profile_detail'),

    # ── Migration Specialist ──────────────────────────────────────────────────
    path('specialist/apply/', MigrationSpecialistApplyView.as_view(), name='specialist_apply'),
    path('specialist/my-application/', MigrationSpecialistApplicationStatusView.as_view(), name='specialist_application_status'),

    # ── Property Endpoints ────────────────────────────────────────────────────
    path('properties/', PropertyListCreateView.as_view(), name='property_list_create'),
    path('properties/search/', PropertySearchView.as_view(), name='property_search'),
    path('properties/<str:pk>/', PropertyDetailView.as_view(), name='property_detail'),
    path('properties/<str:pk>/publish/', PublishPropertyView.as_view(), name='property_publish'),
    path('properties/<str:pk>/upload-images/', UploadPropertyImageView.as_view(), name='property_upload_images'),
    path('properties/<str:pk>/images/<str:image_id>/', DeletePropertyImageView.as_view(), name='property_delete_image'),

    # ── Admin Provider Approval Endpoints ─────────────────────────────────────
    path('admin/providers/pending/', AdminProviderPendingApprovalsView.as_view(), name='admin_providers_pending'),
    path('admin/providers/approvals/', AdminProviderAllApprovalsView.as_view(), name='admin_providers_all'),
    path('admin/providers/stats/', AdminProviderStatsView.as_view(), name='admin_provider_stats'),
    path('admin/providers/<str:pk>/approval-detail/', AdminProviderApprovalDetailView.as_view(), name='admin_provider_approval_detail'),
    path('admin/providers/<str:pk>/process-approval/', AdminProcessProviderApprovalView.as_view(), name='admin_process_provider_approval'),

    # ── Chaperone Endpoints ───────────────────────────────────────────────────
    path('chaperones/available/', AvailableChaperonesView.as_view(), name='available_chaperones'),
    path('<str:pk>/broadcast-chaperone/', BroadcastChaperoneServiceView.as_view(), name='broadcast_chaperone'),

    # ── Immigration Officers ──────────────────────────────────────────────────
    path('immigration-officers/', ImmigrationOfficersView.as_view(), name='immigration_officers'),

    # Dynamic routes must come last so static dashboard routes are not treated as IDs.
    path('<str:pk>/claim/', ClaimServiceView.as_view(), name='claim_service'),
    path('<str:pk>/broadcast/', BroadcastServiceView.as_view(), name='broadcast_service'),

    # ── Route Directions (Uber-style road route for the map) ────────────────
    path('route/', RouteDirectionsView.as_view(), name='route_directions'),
    path('<str:pk>/driver-view/', DriverServiceRequestDetailView.as_view(), name='driver_service_detail'),
    path('<str:pk>/', ServiceRequestDetailView.as_view(), name='service_detail'),
]