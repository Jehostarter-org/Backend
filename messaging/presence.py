"""
messaging/presence.py

Global user-presence tracking used by the DM/messaging app.

Online state lives in the Django cache (Redis in production, LocMem locally)
as a per-user key with a TTL. The NotificationConsumer is the presence source
of truth: while a user's notification WebSocket is alive it refreshes the key
every 30s (driven by the client ping), so an expired key means the user is
offline — even if a disconnect frame was never delivered (crash / network drop).

Status transitions are broadcast to the 'presence' channel group, which every
NotificationConsumer listens to and forwards to its client as a
`{ type: 'presence', user_id, is_online }` frame. REST serializers read the
same cache keys, so inbox/conversation payloads always carry `is_online`.
"""

import logging
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.core.cache import cache

logger = logging.getLogger(__name__)

PRESENCE_GROUP = 'presence'
PRESENCE_TTL = 120  # seconds — client pings every 30s => ~4 missed pings


def _online_key(user_id):
    return f'presence:online:{user_id}'


# ── Sync helpers (REST serializers / views) ─────────────────────────────────
def user_is_online(user_id):
    """True if user_id emitted a presence heartbeat within the TTL window."""
    if user_id is None:
        return False
    try:
        return cache.get(_online_key(user_id)) is not None
    except Exception as e:
        logger.warning('[presence] cache.get failed for %s: %s', user_id, e)
        return False


def _mark_online(user_id):
    key = _online_key(user_id)
    was_online = cache.get(key) is not None
    try:
        cache.set(key, '1', timeout=PRESENCE_TTL)
    except Exception as e:
        logger.warning('[presence] cache.set failed for %s: %s', user_id, e)
        was_online = True  # avoid status flip-flop on cache errors
    return was_online


def _mark_offline(user_id):
    key = _online_key(user_id)
    was_online = cache.get(key) is not None
    try:
        cache.delete(key)
    except Exception as e:
        logger.warning('[presence] cache.delete failed for %s: %s', user_id, e)
    return was_online


# ── Async wrappers (WebSocket consumers) ────────────────────────────────────
mark_online  = database_sync_to_async(_mark_online)
mark_offline = database_sync_to_async(_mark_offline)


async def broadcast_presence(user_id, is_online):
    """Fan a presence transition out to every connected client."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    await channel_layer.group_send(
        PRESENCE_GROUP,
        {
            'type':      'presence_update',
            'user_id':   str(user_id),
            'is_online': bool(is_online),
        },
    )