import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


class AvailableServicesConsumer(AsyncWebsocketConsumer):
    """
    Drivers connect here to receive real-time job notifications.
    Group key: available_services_{country_code}_{city}_{service_type}
    e.g.      available_services_NG_lagos_airport_pickup
    """

    async def connect(self):
        try:
            token_str = self._get_token()
            if not token_str:
                logger.warning('[WS Services] no token — closing')
                await self.close(code=4001)
                return

            self.user = await self._get_user(token_str)
            if not self.user:
                logger.warning('[WS Services] invalid token — closing')
                await self.close(code=4001)
                return

            # Get all service types this driver is registered for in their city
            self.groups = await self._get_driver_groups()
            if not self.groups:
                logger.warning('[WS Services] %s has no active driver profiles — closing', self.user.username)
                await self.close(code=4003)
                return

            for group in self.groups:
                await self.channel_layer.group_add(group, self.channel_name)

            await self.accept()
            logger.info('[WS Services] %s connected to %s', self.user.username, self.groups)
        except Exception as e:
            logger.error('[WS Services] connect error: %s', e, exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, code):
        if hasattr(self, 'groups'):
            for group in self.groups:
                await self.channel_layer.group_discard(group, self.channel_name)

    async def receive(self, text_data):
        pass  # drivers only receive, never send

    # ── Event handler — called by group_send from the view ───────────────────

    async def new_service_request(self, event):
        await self.send(text_data=json.dumps({
            'type':    'new_service_request',
            'payload': event['payload'],
        }))

    async def service_claimed(self, event):
        await self.send(text_data=json.dumps({
            'type':    'service_claimed',
            'payload': event['payload'],
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
            from rest_framework_simplejwt.tokens import AccessToken
            data    = AccessToken(token_str)
            user_id = data['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.warning('[WS Services] auth failed: %s', e)
            return None

    @database_sync_to_async
    def _get_driver_groups(self):
        from .models import ServiceProviderProfile
        profiles = ServiceProviderProfile.objects.filter(
            user=self.user,
            is_active=True,
            approval_status='approved',
        )
        groups = []
        for p in profiles:
            if not p.country_code:
                continue
            # Airport pickups are broadcast to every driver in the AIRPORT's
            # country (the rider may live elsewhere), so drivers also join a
            # country-wide group: available_services_{country}_all_{service_type}
            if p.service_type == 'airport_pickup':
                groups.append(
                    f'available_services_{p.country_code}_all_{p.service_type}'
                )
            if p.city:
                groups.append(
                    f'available_services_{p.country_code}_{p.city.lower()}_{p.service_type}'
                )
        return groups