"""
Utilities to broadcast community events via Django Channels.
"""

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def broadcast_to_community(community_id: str, event_type: str, payload: dict):
    """Send an event to all WebSocket clients connected to a community group."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"community_{community_id}",
        {"type": event_type, **payload},
    )


def broadcast_global_event(event_type: str, payload: dict):
    """Send a global community event to all clients in the community lobby."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "community_lobby",
        {"type": event_type, **payload},
    )


def broadcast_to_user(user_id: str, event_type: str, payload: dict):
    """Send an event to a specific user's notification group."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_notifications_{user_id}",
        {"type": event_type, **payload},
    )


def broadcast_to_admins(event_type: str, payload: dict):
    """Send an event to all admin portal support clients connected to support_admins."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "support_admins",
        {"type": event_type, **payload},
    )
