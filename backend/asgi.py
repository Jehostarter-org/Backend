"""
backend/asgi.py
"""

import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from strawberry.channels import GraphQLWSConsumer   # ← capital WS, capital C
from schema.schema import schema

websocket_urlpatterns = [
    re_path(r'ws/graphql/$', GraphQLWSConsumer.as_asgi(schema=schema)),
]

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})