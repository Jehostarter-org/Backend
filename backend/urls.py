"""
backend/urls.py

Adds the GraphQL endpoint alongside your existing REST API.
Both coexist — REST is not replaced, GraphQL is additive.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from strawberry.django.views import AsyncGraphQLView
from schema.schema import schema

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Existing REST API routes ──────────────────────────────────────────────
    path('api/users/',         include('users.urls')),
    path('api/memberships/',   include('memberships.urls')),
    path('api/shops/',         include('shops.urls')),
    path('api/services/',      include('services.urls')),
    path('api/community/',     include('community.urls')),
    path('api/notifications/', include('notifications.urls')),

    # ── GraphQL endpoint (HTTP for queries/mutations + GraphiQL playground) ──
    # Visit http://localhost:8000/graphql/ in your browser for the interactive IDE
    path('graphql/', AsyncGraphQLView.as_view(schema=schema)),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# WebSocket connections are handled in asgi.py, not here.
# The route /ws/graphql/ is defined in asgi.py's URLRouter.