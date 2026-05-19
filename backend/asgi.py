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

websocket_urlpatterns = [
    re_path(r'.*graphql.*', GraphQLWSConsumer.as_asgi(schema=schema)),
    re_path(r'.*notifications.*', NotificationConsumer.as_asgi()),
]

print("Routes registered:", websocket_urlpatterns)

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})