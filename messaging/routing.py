from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r'^ws/messaging/(?P<conversation_id>[^/]+)/$',
        consumers.ChatConsumer.as_asgi(),
    ),
    re_path(
        r'^ws/support/admins/$',
        consumers.SupportAdminsConsumer.as_asgi(),
    ),
]
