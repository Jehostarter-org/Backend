from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt

from strawberry.django.views import AsyncGraphQLView
from schema.schema import schema

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── GraphQL (HTTP — queries + mutations) ──────────────────────────────────
    # csrf_exempt because clients authenticate via Bearer token not CSRF cookie.
    # AsyncGraphQLView serves GraphiQL playground at http://localhost:8000/graphql/
    path('graphql/', csrf_exempt(AsyncGraphQLView.as_view(schema=schema))),

    # ── REST API ──────────────────────────────────────────────────────────────
    path('api/users/',         include('users.urls')),
    path('api/memberships/',   include('memberships.urls')),
    path('api/shops/',         include('shops.urls')),
    path('api/services/',      include('services.urls')),
    path('api/community/',     include('community.urls')),
    path('api/notifications/', include('notifications.urls')),
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# WebSocket routes are in backend/asgi.py — not here.