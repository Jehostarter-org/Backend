from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt
from django.views.static import serve

import custom_admin  # noqa: F401 — superuser-friendly admin + site branding
from strawberry.django.views import AsyncGraphQLView
from schema.schema import schema
from users.views import VerifyEmailView, ResendVerificationEmailView
from users.location_search_view import LocationSearchView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from memberships.views import (
    CheckEligibilityExistsView,
    CheckGoldEligibilityDestinationView,
    CheckGoldEligibilityHomeView,
    AdminEligibilityListAllView,
    AdminEligibilityDetailView,
    AdminProcessEligibilityView,
    AdminEligibilityStatsView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('portal/', include('portal.urls')),

    # Health check
    path('health/', include('health.urls')),

    # API Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ── GraphQL (HTTP — queries + mutations) ──────────────────────────────────
    # csrf_exempt because clients authenticate via Bearer token not CSRF cookie.
    # AsyncGraphQLView serves GraphiQL playground at http://localhost:8000/graphql/
    path('graphql/', csrf_exempt(AsyncGraphQLView.as_view(schema=schema))),

    # ── REST API ──────────────────────────────────────────────────────────────
    # Email verification (registered here so they are always available)
    path('api/users/verify-email/',        VerifyEmailView.as_view(),               name='verify_email'),
    path('api/users/resend-verification/', ResendVerificationEmailView.as_view(),    name='resend_verification'),
    path('api/location-search/',           LocationSearchView.as_view(),             name='location_search'),
    path('api/users/',                     include('users.urls')),
    path('api/memberships/',               include('memberships.urls')),
    # Eligibility check endpoints (direct routes matching frontend expectations)
    path('api/plan/gold/eligibility/check/destination', CheckGoldEligibilityDestinationView.as_view(), name='gold_eligibility_destination_direct'),
    path('api/plan/gold/eligibility/check/home',        CheckGoldEligibilityHomeView.as_view(),        name='gold_eligibility_home_direct'),
    path('api/plan/gold/eligibility/exists',            CheckEligibilityExistsView.as_view(),          name='eligibility_exists_direct'),

    # Admin: review gold-eligibility submissions (direct routes, mirror the /api/plan/... pattern above)
    path('api/plan/admin/eligibility/',                  AdminEligibilityListAllView.as_view(),        name='admin_eligibility_list_direct'),
    path('api/plan/admin/eligibility/stats/',            AdminEligibilityStatsView.as_view(),          name='admin_eligibility_stats_direct'),
    path('api/plan/admin/eligibility/<str:pk>/',         AdminEligibilityDetailView.as_view(),         name='admin_eligibility_detail_direct'),
    path('api/plan/admin/eligibility/<str:pk>/process/', AdminProcessEligibilityView.as_view(),        name='admin_process_eligibility_direct'),
    path('api/shops/',                     include('shops.urls')),
    path('api/services/',                  include('services.urls')),
    path('api/community/',                 include('community.urls')),
    path('api/notifications/',             include('notifications.urls')),
    path('api/messaging/',                 include('messaging.urls', namespace='messaging')),  # ← NEW
]

# ── Media files ───────────────────────────────────────────────────────────────
# NOTE: Django's static() helper silently returns an empty urlpatterns list
# whenever settings.DEBUG is False — this is baked into Django itself
# (django/conf/urls/static.py), regardless of how/where you call it.
# Since Dokploy's Traefik proxy doesn't serve /media/ natively, and DEBUG=False
# in production, we wire up django.views.static.serve directly instead so
# media is actually served regardless of DEBUG.
#
# Caveat: django.views.static.serve is NOT production-hardened (no caching
# headers, not built for high traffic). This unblocks things now; longer term,
# have Traefik serve /media/ directly from the host volume path instead.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

# Static files only need Django's help in local dev (DEBUG=True) —
# in production, WhiteNoise middleware handles /static/ already.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# WebSocket routes are in backend/asgi.py — not here.