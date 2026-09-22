"""
notifications/consumers.py

Full WebSocket consumer with location.updated handler.
When location changes, frontend receives the event and re-fetches nearby shops.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.utils import timezone
from messaging.presence import (
    PRESENCE_GROUP,
    mark_online,
    mark_offline,
    broadcast_presence,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        token_str = self._get_token()
        if not token_str:
            await self.close()
            return

        self.user = await self._get_user(token_str)
        if not self.user:
            await self.close()
            return

        self.group_name = f'user_{self.user.id}'
        self.notifications_group_name = f'user_notifications_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.notifications_group_name, self.channel_name)
        await self.channel_layer.group_add(PRESENCE_GROUP, self.channel_name)
        await self.accept()

        # ── Presence: mark online and announce the transition if it's new ─────
        await self._touch_last_seen()
        was_online = await mark_online(self.user.id)
        if not was_online:
            await broadcast_presence(self.user.id, True)

        unread = await self._unread_count()
        logger.info("[WS] Connected. Unread: %s", unread)
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'unread_count': unread,
            'unread': unread,
        }))

    async def disconnect(self, code):
        logger.info("[WS] Disconnected. code=%s", code)
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, 'notifications_group_name'):
            await self.channel_layer.group_discard(self.notifications_group_name, self.channel_name)
        if hasattr(self, 'notifications_group_name'):
            await self.channel_layer.group_discard(PRESENCE_GROUP, self.channel_name)
        if hasattr(self, 'user'):
            await self._touch_last_seen()
            was_online = await mark_offline(self.user.id)
            if was_online:
                await broadcast_presence(self.user.id, False)

    async def receive(self, text_data):
        # Every frame (client pings every 30s) keeps the presence heartbeat alive.
        if hasattr(self, 'user'):
            was_online = await mark_online(self.user.id)
            if not was_online:
                await broadcast_presence(self.user.id, True)

    # ── Notification event ────────────────────────────────────────────────────

    async def notification_message(self, event):
        await self.send(text_data=json.dumps({
            'type':    'notification',
            'id':      event.get('id'),
            'title':   event.get('title'),
            'message': event.get('message'),
            'link':    event.get('link'),
        }))

    async def new_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'payload': event.get('payload', {}),
        }))

    # ── New conversation event ─────────────────────────────────────────────────

    async def new_conversation(self, event):
        await self.send(text_data=json.dumps({
            'type':         'new_conversation',
            'conversation': event.get('conversation'),
        }))

    # ── Presence event ───────────────────────────────────────────────────────

    async def presence_update(self, event):
        """Forward `{ user_id, is_online }` transitions to every connected client."""
        await self.send(text_data=json.dumps({
            'type':      'presence',
            'user_id':   event.get('user_id'),
            'is_online': bool(event.get('is_online')),
        }))

    # ── Location updated event ────────────────────────────────────────────────

    async def location_updated(self, event):
        """
        Fired after user location is saved (GPS, IP, or timezone detection).
        Frontend listens for this and immediately re-fetches nearby shops.

        Frontend handler example:
            ws.onmessage = (e) => {
              const data = JSON.parse(e.data);
              if (data.type === 'location.updated') {
                refetchNearbyShops();   // re-run nearbyShops GraphQL query
              }
            };
        """
        await self.send(text_data=json.dumps({
            'type':      'location.updated',
            'latitude':  event['latitude'],
            'longitude': event['longitude'],
            'source':    event.get('source', ''),
        }))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_token(self):
        qs = self.scope.get('query_string', b'').decode()
        logger.debug("[WS] query_string raw: %s", qs[:80])
        for part in qs.split('&'):
            if part.startswith('token='):
                token = part[6:]
                logger.debug("[WS] token present: True, length: %s", len(token))
                return token
        logger.debug("[WS] token present: False")
        return None

    @database_sync_to_async
    def _get_user(self, token_str):
        try:
            data    = AccessToken(token_str)
            user_id = data['user_id']
            logger.debug("[WS] token user_id: %s", user_id)
            user = User.objects.get(id=user_id)
            logger.debug("[WS] user resolved: %s", user.email)
            return user
        except Exception as e:
            logger.warning("[WS] auth failed: %s", e)
            return None

    @database_sync_to_async
    def _unread_count(self):
        return self.user.notifications.filter(is_read=False).count()

    @database_sync_to_async
    def _touch_last_seen(self):
        try:
            self.user.last_seen = timezone.now()
            self.user.save(update_fields=['last_seen'])
        except Exception as e:
            logger.warning("[WS] last_seen update failed: %s", e)
