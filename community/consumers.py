"""
community/consumers.py

WebSocket consumer for real-time community group chat.

Connection URL (set in routing.py):
    ws://<host>/ws/community/<community_id>/?token=<jwt>

Flow:
    1. Client connects with JWT token in query string
    2. Consumer validates token → resolves user → checks membership
    3. User joins the channel group for that community
    4. Any message sent by one member is broadcast to all members in real time
    5. Message is saved to the database so history persists
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from .models import Community, CommunityMember, Message

User = get_user_model()


class CommunityConsumer(AsyncWebsocketConsumer):

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self):
        self.community_id = self.scope['url_route']['kwargs']['community_id']
        self.group_name   = f'community_{self.community_id}'

        # Auth
        token_str = self._get_token()
        if not token_str:
            await self.close(code=4001)
            return

        self.user = await self._get_user(token_str)
        if not self.user:
            await self.close(code=4001)
            return

        # Membership check
        is_member = await self._is_member()
        if not is_member:
            await self.close(code=4003)
            return

        # Join channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        print(f'[WS Community] {self.user.username} connected to {self.community_id}')

        # Notify the room that this user joined
        await self.channel_layer.group_send(self.group_name, {
            'type':     'user_joined',
            'username': self.user.username,
            'user_id':  str(self.user.id),
        })

    async def disconnect(self, code):
        print(f'[WS Community] {getattr(self, "user", "unknown")} disconnected. code={code}')
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # ── Receive from client ───────────────────────────────────────────────────

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', 'message')

        if msg_type == 'message':
            content = (data.get('content') or '').strip()
            if not content:
                return

            # Save to DB
            message = await self._save_message(content)

            # Broadcast to all members in the community channel group
            await self.channel_layer.group_send(self.group_name, {
                'type':           'chat_message',
                'id':             str(message.id),
                'content':        message.content,
                'sender_id':      str(self.user.id),
                'sender_username': self.user.username,
                'sender_avatar':  await self._get_avatar(),
                'created_at':     message.created_at.isoformat(),
            })

        elif msg_type == 'typing':
            # Broadcast typing indicator (not saved)
            await self.channel_layer.group_send(self.group_name, {
                'type':     'typing_indicator',
                'username': self.user.username,
                'user_id':  str(self.user.id),
            })

    # ── Channel layer event handlers ──────────────────────────────────────────

    async def chat_message(self, event):
        """Broadcast a new chat message to this WebSocket client."""
        await self.send(text_data=json.dumps({
            'type':            'message',
            'id':              event['id'],
            'content':         event['content'],
            'sender_id':       event['sender_id'],
            'sender_username': event['sender_username'],
            'sender_avatar':   event['sender_avatar'],
            'created_at':      event['created_at'],
        }))

    async def typing_indicator(self, event):
        """Forward typing indicator — skip if it's from this user."""
        if event['user_id'] != str(self.user.id):
            await self.send(text_data=json.dumps({
                'type':     'typing',
                'username': event['username'],
            }))

    async def user_joined(self, event):
        """Notify all clients when a new member connects."""
        await self.send(text_data=json.dumps({
            'type':     'user_joined',
            'username': event['username'],
            'user_id':  event['user_id'],
        }))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_token(self):
        qs = self.scope.get('query_string', b'').decode()
        for part in qs.split('&'):
            if part.startswith('token='):
                return part[6:]
        return None

    @database_sync_to_async
    def _get_user(self, token_str):
        try:
            data    = AccessToken(token_str)
            user_id = data['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            print(f'[WS Community] auth failed: {e}')
            return None

    @database_sync_to_async
    def _is_member(self):
        return CommunityMember.objects.filter(
            community_id=self.community_id,
            user=self.user,
            is_banned=False,
        ).exists()

    @database_sync_to_async
    def _save_message(self, content):
        return Message.objects.create(
            community_id=self.community_id,
            sender=self.user,
            content=content,
        )

    @database_sync_to_async
    def _get_avatar(self):
        avatar = getattr(self.user, 'avatar', None) or getattr(self.user, 'profile_picture', None)
        if avatar:
            try:
                return avatar.url
            except Exception:
                pass
        return None