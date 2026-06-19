from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt

import custom_admin  # noqa: F401 — superuser-friendly admin + site branding
from strawberry.django.views import AsyncGraphQLView
from schema.schema import schema
from users.views import VerifyEmailView, ResendVerificationEmailView
from users.location_search_view import LocationSearchView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from memberships.views import CheckEligibilityExistsView, CheckGoldEligibilityDestinationView, CheckGoldEligibilityHomeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('portal/', include('portal.urls')),

    # ── API Docs ───────────────────────────────────────────────────────────────
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
    path('api/shops/',                     include('shops.urls')),
    path('api/services/',                  include('services.urls')),
    path('api/community/',                 include('community.urls')),
    path('api/notifications/',             include('notifications.urls')),
    path('api/messaging/',                 include('messaging.urls', namespace='messaging')),  # ← NEW
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# WebSocket routes are in backend/asgi.py — not here.