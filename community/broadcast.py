"""
Utilities to broadcast community events via Django Channels.

All broadcasts are fire-and-forget: a Redis outage is logged as a warning
and never raised, so realtime pushes can't fail the request that triggered
them (see messaging/signals.py for the same policy on notifications).
"""

import logging

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def _group_send(group: str, message: dict):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError('channel layer is not configured')
        async_to_sync(channel_layer.group_send)(group, message)
    except Exception as exc:
        logger.warning('WS broadcast to %s failed: %s', group, exc)


def broadcast_to_community(community_id: str, event_type: str, payload: dict):
    """Send an event to all WebSocket clients connected to a community group."""
    _group_send(f"community_{community_id}", {"type": event_type, **payload})


def broadcast_global_event(event_type: str, payload: dict):
    """Send a global community event to all clients in the community lobby."""
    _group_send("community_lobby", {"type": event_type, **payload})


def broadcast_to_user(user_id: str, event_type: str, payload: dict):
    """Send an event to a specific user's notification group."""
    _group_send(f"user_notifications_{user_id}", {"type": event_type, **payload})


def broadcast_to_admins(event_type: str, payload: dict):
    """Send an event to all admin portal support clients connected to support_admins."""
    _group_send("support_admins", {"type": event_type, **payload})
