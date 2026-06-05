# ─── backend/asgi.py  (replace your existing file) ───────────────────────────
#
# Add the messaging WebSocket routes to your ASGI application.

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

django_asgi_app = get_asgi_application()

# Import AFTER django setup
from channels.auth import AuthMiddlewareStack
from community.routing import websocket_urlpatterns as community_ws   # existing
from messaging.routing import websocket_urlpatterns as messaging_ws   # new

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                community_ws + messaging_ws   # merge both WS route lists
            )
        )
    ),
})


# ─── backend/urls.py  (add this line to your urlpatterns) ─────────────────────
#
#   path('api/messaging/', include('messaging.urls', namespace='messaging')),
#
# Example full urlpatterns:
#
# from django.contrib import admin
# from django.urls import path, include
#
# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path('api/users/',        include('users.urls')),
#     path('api/memberships/',  include('memberships.urls')),
#     path('api/shops/',        include('shops.urls')),
#     path('api/services/',     include('services.urls')),
#     path('api/community/',    include('community.urls')),
#     path('api/notifications/',include('notifications.urls')),
#     path('api/messaging/',    include('messaging.urls', namespace='messaging')),  # ← ADD
# ]


# ─── backend/settings.py  (add 'messaging' to INSTALLED_APPS) ─────────────────
#
# INSTALLED_APPS = [
#     ...
#     # ── Local Apps ──
#     'users',
#     'memberships',
#     'shops',
#     'services',
#     'community',
#     'notifications',
#     'portal',
#     'messaging',   # ← ADD
# ]
