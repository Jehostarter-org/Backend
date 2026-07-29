import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()


from strawberry.channels import GraphQLWSConsumer
from schema.schema import schema
from notifications.consumers import NotificationConsumer
from community.routing import community_websocket_urlpatterns
from messaging.routing import websocket_urlpatterns as messaging_ws_urlpatterns
from services.routing import services_websocket_urlpatterns

websocket_urlpatterns = [
    # ── GraphQL subscriptions ────────────────────────────────────────────────
    re_path(r'^ws/graphql/$', GraphQLWSConsumer.as_asgi(schema=schema)),
    # ── Notifications ───────────────────────────────────────────────────────
    re_path(r'^ws/notifications/$', NotificationConsumer.as_asgi()),
    # ── Community chat ──────────────────────────────────────────────────────
    *community_websocket_urlpatterns,
    # ── Direct messages ─────────────────────────────────────────────────────
    *messaging_ws_urlpatterns,
    # Services — driver job notifications
    *services_websocket_urlpatterns,
]


application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(websocket_urlpatterns),
})