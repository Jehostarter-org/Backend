"""
notifications/consumers.py

Full WebSocket consumer with location.updated handler.
When location changes, frontend receives the event and re-fetches nearby shops.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()


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
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        unread = await self._unread_count()
        print(f"[WS] Connected. Unread: {unread}")
        await self.send(text_data=json.dumps({'type': 'connected', 'unread': unread}))

    async def disconnect(self, code):
        print(f"[WS] Disconnected. code={code}")
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    # ── Notification event ────────────────────────────────────────────────────

    async def notification_message(self, event):
        await self.send(text_data=json.dumps({
            'type':    'notification',
            'id':      event.get('id'),
            'title':   event.get('title'),
            'message': event.get('message'),
            'link':    event.get('link'),
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
        print(f"[WS] query_string raw: {qs[:80]}")
        for part in qs.split('&'):
            if part.startswith('token='):
                token = part[6:]
                print(f"[WS] token present: True, length: {len(token)}")
                return token
        print("[WS] token present: False")
        return None

    @database_sync_to_async
    def _get_user(self, token_str):
        try:
            data    = AccessToken(token_str)
            user_id = data['user_id']
            print(f"[WS] token user_id: {user_id}")
            user = User.objects.get(id=user_id)
            print(f"[WS] user resolved: {user.email}")
            return user
        except Exception as e:
            print(f"[WS] auth failed: {e}")
            return None

    @database_sync_to_async
    def _unread_count(self):
        return self.user.notifications.filter(is_read=False).count()