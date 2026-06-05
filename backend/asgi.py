import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

print("ASGI loading routes...")

from strawberry.channels import GraphQLWSConsumer
from schema.schema import schema
from notifications.consumers import NotificationConsumer
from community.routing import community_websocket_urlpatterns
from messaging.routing import websocket_urlpatterns as messaging_ws_urlpatterns

websocket_urlpatterns = [
    # ── GraphQL subscriptions ────────────────────────────────────────────────
    re_path(r'^ws/graphql/$', GraphQLWSConsumer.as_asgi(schema=schema)),
    # ── Notifications ───────────────────────────────────────────────────────
    re_path(r'^ws/notifications/$', NotificationConsumer.as_asgi()),
    # ── Community chat ──────────────────────────────────────────────────────
    *community_websocket_urlpatterns,
    # ── Direct messages ─────────────────────────────────────────────────────
    *messaging_ws_urlpatterns,
]

print("Routes registered:", websocket_urlpatterns)

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})