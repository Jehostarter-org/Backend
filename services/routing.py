from django.urls import re_path
from .consumers import AvailableServicesConsumer

services_websocket_urlpatterns = [
    re_path(r'^ws/services/available/$', AvailableServicesConsumer.as_asgi()),
]