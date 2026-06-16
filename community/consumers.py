"""
community/consumers.py

Supported client → server message types
----------------------------------------
  { "type": "message",  "content": "...", "reply_to_id": "<id>|null" }
  { "type": "typing" }
  { "type": "delete_message", "message_id": "<id>" }

Supported server → client message types
----------------------------------------
  { "type": "message",         ..., "reply_to": { id, sender_username, content } | null }
  { "type": "typing",          ... }
  { "type": "user_joined",     "username": "...", "user_id": "..." }
  { "type": "user_left",       "username": "...", "user_id": "..." }
  { "type": "message_deleted", "message_id": "<id>", "deleted_by": "<user_id>" }
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from .models import Community, CommunityMember, Message
from .message_notifications import notify_community_members

User = get_user_model()
logger = logging.getLogger(__name__)


class CommunityConsumer(AsyncWebsocketConsumer):

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self):
        self.community_id = self.scope['url_route']['kwargs']['community_id']
        self.group_name   = f'community_{self.community_id}'

        token_str = self._get_token()
        if not token_str:
            await self.close(code=4001)
            return

        self.user = await self._get_user(token_str)
        if not self.user:
            await self.close(code=4001)
            return

        if not await self._is_member():
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info('[WS Community] %s connected to %s', self.user.username, self.community_id)

        # Notify everyone (including self) that this user is now online
        await self.channel_layer.group_send(self.group_name, {
            'type':     'user_joined',
            'username': self.user.username,
            'user_id':  str(self.user.id),
        })

    async def disconnect(self, code):
        logger.info('[WS Community] %s disconnected. code=%s', getattr(self, 'user', 'unknown'), code)
        if hasattr(self, 'group_name'):
            if hasattr(self, 'user') and self.user is not None:
                await self.channel_layer.group_send(self.group_name, {
                    'type':     'user_left',
                    'username': self.user.username,
                    'user_id':  str(self.user.id),
                })
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # ── Receive from client ───────────────────────────────────────────────────

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', 'message')

        if msg_type == 'message':
            content      = (data.get('content') or '').strip()
            reply_to_id  = (data.get('reply_to_id') or '').strip() or None
            if not content:
                return

            message, reply_to_preview = await self._save_message(content, reply_to_id)

            await self.channel_layer.group_send(self.group_name, {
                'type':            'chat_message',
                'id':              str(message.id),
                'content':         message.content,
                'sender_id':       str(self.user.id),
                'sender_username': self.user.username,
                'sender_avatar':   await self._get_avatar(),
                'reply_to':        reply_to_preview,
                'attachment_url':  None,
                'attachment_name': '',
                'attachment_type': '',
                'attachment_size': 0,
                'created_at':      message.created_at.isoformat(),
            })

        elif msg_type == 'typing':
            await self.channel_layer.group_send(self.group_name, {
                'type':     'typing_indicator',
                'username': self.user.username,
                'user_id':  str(self.user.id),
            })

        elif msg_type == 'delete_message':
            message_id = (data.get('message_id') or '').strip()
            if not message_id:
                return

            result = await self._delete_message(message_id)

            if result == 'ok':
                await self.channel_layer.group_send(self.group_name, {
                    'type':       'message_deleted_event',
                    'message_id': message_id,
                    'deleted_by': str(self.user.id),
                })
            elif result == 'forbidden':
                await self.send(text_data=json.dumps({
                    'type':   'error',
                    'detail': 'You cannot delete that message.',
                }))
            else:
                await self.send(text_data=json.dumps({
                    'type':   'error',
                    'detail': 'Message not found.',
                }))

    # ── Channel layer event handlers ──────────────────────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type':            'message',
            'id':              event['id'],
            'content':         event['content'],
            'sender_id':       event['sender_id'],
            'sender_username': event['sender_username'],
            'sender_avatar':   event['sender_avatar'],
            'reply_to':        event.get('reply_to'),
            'attachment_url':  event.get('attachment_url'),
            'attachment_name': event.get('attachment_name', ''),
            'attachment_type': event.get('attachment_type', ''),
            'attachment_size': event.get('attachment_size', 0),
            'created_at':      event['created_at'],
        }))

    async def typing_indicator(self, event):
        if event['user_id'] != str(self.user.id):
            await self.send(text_data=json.dumps({
                'type':     'typing',
                'username': event['username'],
            }))

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type':     'user_joined',
            'username': event['username'],
            'user_id':  event['user_id'],
        }))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type':     'user_left',
            'username': event['username'],
            'user_id':  event['user_id'],
        }))

    async def message_deleted_event(self, event):
        await self.send(text_data=json.dumps({
            'type':       'message_deleted',
            'message_id': event['message_id'],
            'deleted_by': event['deleted_by'],
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
            logger.warning('[WS Community] auth failed: %s', e)
            return None

    @database_sync_to_async
    def _is_member(self):
        return CommunityMember.objects.filter(
            community_id=self.community_id,
            user=self.user,
            is_banned=False,
        ).exists()

    @database_sync_to_async
    def _save_message(self, content, reply_to_id=None):
        reply_to_obj     = None
        reply_to_preview = None

        if reply_to_id:
            try:
                reply_to_obj = Message.objects.select_related('sender').get(
                    pk=reply_to_id,
                    community_id=self.community_id,
                    is_deleted=False,
                )
                reply_to_preview = {
                    'id':              str(reply_to_obj.id),
                    'sender_username': reply_to_obj.sender.username,
                    'content':         (reply_to_obj.content or '')[:80],
                }
            except Message.DoesNotExist:
                pass

        message = Message.objects.create(
            community_id=self.community_id,
            sender=self.user,
            content=content,
            reply_to=reply_to_obj,
        )
        notify_community_members(message)
        return message, reply_to_preview

    @database_sync_to_async
    def _delete_message(self, message_id):
        try:
            message = Message.objects.get(
                pk=message_id,
                community_id=self.community_id,
                is_deleted=False,
            )
        except Message.DoesNotExist:
            return 'not_found'

        is_own   = str(message.sender_id) == str(self.user.id)
        is_admin = CommunityMember.objects.filter(
            community_id=self.community_id,
            user=self.user,
            role__in=['admin', 'moderator'],
            is_banned=False,
        ).exists()

        if not (is_own or is_admin):
            return 'forbidden'

        message.is_deleted = True
        message.save(update_fields=['is_deleted'])
        return 'ok'

    @database_sync_to_async
    def _get_avatar(self):
        avatar = getattr(self.user, 'avatar', None) or getattr(self.user, 'profile_picture', None)
        if avatar:
            try:
                return avatar.url
            except Exception:
                pass
        return None