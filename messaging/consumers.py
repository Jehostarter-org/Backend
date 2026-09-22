import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for a single DM conversation thread.

    Connect:  ws://host/ws/messaging/<conversation_id>/?token=<access_token>
    Auth:     Same JWT query-param pattern as NotificationConsumer.

    Incoming message types:
      { "type": "chat_message", "body": "Hello!", "reply_to_id": 123, "service_card": null }
      { "type": "typing", "is_typing": true }
      { "type": "mark_read" }
      { "type": "delete_message", "message_id": 123 }

    Outgoing message types:
      { "type": "connected",      "unread_count": 3 }
      { "type": "chat_message",   "message": { ... } }
      { "type": "typing",         "user_id": 1, "is_typing": true }
      { "type": "read_receipt",   "user_id": 1, "count": 2 }
      { "type": "message_deleted","message_id": 123 }
      { "type": "error",          "detail": "..." }
    """

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'

        # ── Auth: same pattern as NotificationConsumer ────────────────────────
        token_str = self._get_token()
        if not token_str:
            logger.warning('[Chat WS] No token — rejecting conversation %s', self.conversation_id)
            await self.close()
            return

        self.user = await self._get_user(token_str)
        if not self.user:
            logger.warning('[Chat WS] Invalid token — rejecting conversation %s', self.conversation_id)
            await self.close()
            return

        # ── Authorise: user must be a participant ─────────────────────────────
        if not await self._is_participant():
            logger.warning('[Chat WS] %s not in conversation %s', self.user.email, self.conversation_id)
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        unread = await self._unread_count()
        logger.info('[Chat WS] Connected: %s → conversation %s. Unread: %s', self.user.email, self.conversation_id, unread)

        await self.send(text_data=json.dumps({
            'type':         'connected',
            'unread_count': unread,
        }))

    async def disconnect(self, close_code):
        logger.info('[Chat WS] Disconnected. code=%s', close_code)
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({'type': 'error', 'detail': 'Invalid JSON'}))
            return

        msg_type = data.get('type')

        if msg_type == 'chat_message':
            body         = (data.get('body') or '').strip()
            service_card = data.get('service_card')
            reply_to_id  = data.get('reply_to_id')

            if not body and not service_card:
                await self.send(text_data=json.dumps({'type': 'error', 'detail': 'Empty message.'}))
                return

            message = await self._save_message(body, service_card, reply_to_id)
            if message:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {'type': 'broadcast_message', 'message': message}
                )
                # Keep open admin support inboxes in sync
                if await self._is_support_conversation():
                    await self.channel_layer.group_send(
                        'support_admins',
                        {'type': 'support_update', 'conversation_id': self.conversation_id}
                    )

        elif msg_type == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type':      'broadcast_typing',
                    'user_id':   self.user.id,
                    'is_typing': data.get('is_typing', True),
                }
            )

        elif msg_type == 'mark_read':
            count = await self._mark_messages_read()
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'broadcast_read', 'user_id': self.user.id, 'count': count}
            )

        elif msg_type == 'delete_message':
            message_id = data.get('message_id')
            deleted = await self._delete_message(message_id)
            if deleted:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {'type': 'broadcast_delete', 'message_id': message_id}
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'detail': 'Could not delete this message.',
                }))

    # ── Group event handlers ──────────────────────────────────────────────────

    async def broadcast_message(self, event):
        await self.send(text_data=json.dumps({
            'type':    'chat_message',
            'message': event['message'],
        }))

    async def broadcast_typing(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type':      'typing',
                'user_id':   event['user_id'],
                'is_typing': event['is_typing'],
            }))

    async def broadcast_read(self, event):
        await self.send(text_data=json.dumps({
            'type':    'read_receipt',
            'user_id': event['user_id'],
            'count':   event['count'],
        }))

    async def broadcast_delete(self, event):
        await self.send(text_data=json.dumps({
            'type':       'message_deleted',
            'message_id': event['message_id'],
        }))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_token(self):
        """Extract JWT from query string — matches NotificationConsumer pattern."""
        qs = self.scope.get('query_string', b'').decode()
        logger.debug('[Chat WS] query_string: %s', qs[:80])
        for part in qs.split('&'):
            if part.startswith('token='):
                token = part[6:]
                logger.debug('[Chat WS] token present: True, length: %s', len(token))
                return token
        logger.debug('[Chat WS] token present: False')
        return None

    @database_sync_to_async
    def _get_user(self, token_str):
        """Validate JWT and return User — matches NotificationConsumer pattern."""
        try:
            data    = AccessToken(token_str)
            user_id = data['user_id']
            logger.debug('[Chat WS] token user_id: %s', user_id)
            user = User.objects.get(id=user_id)
            logger.debug('[Chat WS] user resolved: %s', user.email)
            return user
        except Exception as e:
            logger.warning('[Chat WS] auth failed: %s', e)
            return None

    @database_sync_to_async
    def _is_participant(self):
        from .models import Conversation
        try:
            conversation = Conversation.objects.get(pk=self.conversation_id)
        except Conversation.DoesNotExist:
            return False
        # A stored participant, or any staff member on a support thread, may join.
        if conversation.participants.filter(pk=self.user.pk).exists():
            return True
        return conversation.is_support() and self.user.is_staff

    @database_sync_to_async
    def _is_support_conversation(self):
        from .models import Conversation
        return Conversation.objects.filter(
            pk=self.conversation_id, service_type='support'
        ).exists()

    @database_sync_to_async
    def _save_message(self, body, service_card, reply_to_id=None):
        from .models import Conversation, Message, MessageAttachment
        try:
            conversation = Conversation.objects.get(pk=self.conversation_id)
        except Conversation.DoesNotExist:
            return None

        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.select_related('sender').filter(
                pk=reply_to_id,
                conversation=conversation,
            ).first()

        msg = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            reply_to=reply_to,
            body=body,
            service_card=service_card,
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        attachments = [
            {
                'id': att.id,
                'url': att.file.url if att.file else '',
                'filename': att.filename,
                'filesize': att.filesize,
            }
            for att in msg.attachments.all()
        ]

        return {
            'id':           msg.id,
            'body':         msg.body,
            'sender': {
                'id':        self.user.id,
                'full_name': self.user.get_full_name() or self.user.email,
            },
            'reply_to': self._reply_preview(reply_to),
            'service_card': msg.service_card,
            'attachments':  attachments,
            'is_read':      msg.is_read,
            'created_at':   msg.created_at.isoformat(),
        }

    def _reply_preview(self, message):
        if not message:
            return None
        return {
            'id': message.id,
            'sender': {
                'id': message.sender_id,
                'full_name': message.sender.get_full_name() or message.sender.email,
            },
            'body': message.body,
            'created_at': message.created_at.isoformat(),
        }

    @database_sync_to_async
    def _delete_message(self, message_id):
        from .models import Message
        if not message_id:
            return False
        deleted, _ = Message.objects.filter(
            pk=message_id,
            conversation_id=self.conversation_id,
            sender=self.user,
        ).delete()
        return deleted > 0

    @database_sync_to_async
    def _mark_messages_read(self):
        from .models import Conversation
        conversation = Conversation.objects.get(pk=self.conversation_id)
        return conversation.messages.filter(
            is_read=False
        ).exclude(sender=self.user).update(is_read=True)

    @database_sync_to_async
    def _unread_count(self):
        from .models import Message
        return Message.objects.filter(
            conversation__participants=self.user,
            is_read=False,
        ).exclude(sender=self.user).count()


class SupportAdminsConsumer(AsyncWebsocketConsumer):
    """
    WebSocket that keeps the admin portal "Support inbox" live.

    Connect:  ws://host/ws/support/admins/?token=<access_token>
    Auth:     JWT query-param (same as ChatConsumer); requires an is_staff user.

    Messages pushed to the client:
      { "type": "support_update", "conversation_id": <id> }
    """

    async def connect(self):
        token_str = self._get_token()
        if not token_str:
            logger.warning('[Support WS] No token — rejecting')
            await self.close()
            return

        self.user = await self._get_user(token_str)
        if not self.user or not self.user.is_staff:
            logger.warning('[Support WS] Not an authenticated staff member — rejecting')
            await self.close()
            return

        self.group_name = 'support_admins'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info('[Support WS] Staff connected: %s', self.user.email)

    async def disconnect(self, close_code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Forwarded from broadcast_to_admins(...) via group_send.
    async def support_update(self, event):
        await self.send(text_data=json.dumps({
            'type':            'support_update',
            'conversation_id': event.get('conversation_id'),
        }))

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
            logger.warning('[Support WS] auth failed: %s', e)
            return None
