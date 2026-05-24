"""
community/routing.py

WebSocket URL routing for the community chat consumer.

──────────────────────────────────────────────────────────────────────────────
STEP 1 — Include this in your project-level routing (e.g. myproject/routing.py
         or wherever you registered NotificationConsumer):

    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack
    from django.urls import path

    from notifications.consumers import NotificationConsumer   # your existing one
    from community.routing import community_websocket_urlpatterns

    application = ProtocolTypeRouter({
        'websocket': AuthMiddlewareStack(
            URLRouter([
                path('ws/notifications/', NotificationConsumer.as_asgi()),
                *community_websocket_urlpatterns,              # <-- add this
            ])
        ),
    })

──────────────────────────────────────────────────────────────────────────────
STEP 2 — Run migrations after adding the Message model:

    python manage.py makemigrations community
    python manage.py migrate

──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import re_path
from .consumers import CommunityConsumer

community_websocket_urlpatterns = [
    # ws://<host>/ws/community/<community_id>/?token=<jwt>
    re_path(r'^ws/community/(?P<community_id>[^/]+)/$', CommunityConsumer.as_asgi()),
]