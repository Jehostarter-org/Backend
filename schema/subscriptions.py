"""
schema/subscriptions.py

GraphQL Subscriptions — the real-time layer.
These run over WebSocket. A frontend client subscribes and receives
live pushes whenever something happens on the server.

How it works:
  1. Client connects via WebSocket to /ws/graphql/
  2. Client sends a subscription query (e.g. subscribe to my notifications)
  3. Server registers the client into a Redis channel group
  4. When a mutation broadcasts to that group, ALL subscribed clients receive the event
  5. Strawberry calls the generator's __anext__ and pushes the result to the client
"""

import strawberry
import asyncio
from typing import AsyncGenerator, Optional
from strawberry.types import Info
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async

from .types import NotificationType, PostType, ServiceRequestType
from notifications.models import Notification
from community.models import Post
from services.models import ServiceRequest


channel_layer = get_channel_layer()


@strawberry.type
class Subscription:

    # ─── 1. Live Notifications ────────────────────────────────────────────────
    # Subscribe to real-time notifications for the logged-in user.
    #
    # Frontend usage:
    #   subscription {
    #     myNotifications {
    #       id notificationType title message isRead createdAt
    #     }
    #   }

    @strawberry.subscription
    async def my_notifications(
        self, info: Info
    ) -> AsyncGenerator[NotificationType, None]:
        """
        Push new notifications to the logged-in user in real time.
        Listens on group: user_notifications_{user_id}
        """
        user = info.context.request.user
        if user.is_anonymous:
            return

        group_name = f'user_notifications_{user.id}'

        # Add this WebSocket connection to the user's notification group
        await channel_layer.group_add(group_name, info.context.ws.channel_name)

        try:
            while True:
                # Wait for a message to arrive in this group
                message = await channel_layer.receive(info.context.ws.channel_name)

                if message.get('type') == 'new_notification':
                    payload = message['payload']
                    # Fetch the full notification object from DB
                    try:
                        notif = await sync_to_async(Notification.objects.select_related(
                            'recipient', 'actor'
                        ).get)(id=payload['notification_id'])
                        yield notif
                    except Notification.DoesNotExist:
                        continue

        finally:
            # Clean up when WebSocket disconnects
            await channel_layer.group_discard(group_name, info.context.ws.channel_name)

    # ─── 2. Community Feed ────────────────────────────────────────────────────
    # Subscribe to new posts in a specific community.
    #
    # Frontend usage:
    #   subscription CommunityFeed($communityId: String!) {
    #     communityFeed(communityId: $communityId) {
    #       id content postType author { username } createdAt
    #     }
    #   }

    @strawberry.subscription
    async def community_feed(
        self,
        info: Info,
        community_id: str,
    ) -> AsyncGenerator[PostType, None]:
        """
        Push new posts to all subscribers of a community feed.
        Listens on group: community_feed_{community_id}
        """
        group_name = f'community_feed_{community_id}'

        await channel_layer.group_add(group_name, info.context.ws.channel_name)

        try:
            while True:
                message = await channel_layer.receive(info.context.ws.channel_name)

                if message.get('type') == 'new_post':
                    payload = message['payload']
                    try:
                        post = await sync_to_async(
                            Post.objects.select_related('author', 'community').get
                        )(id=payload['post_id'])
                        yield post
                    except Post.DoesNotExist:
                        continue

        finally:
            await channel_layer.group_discard(group_name, info.context.ws.channel_name)

    # ─── 3. Service Status Updates ────────────────────────────────────────────
    # Subscribe to real-time status changes on a service request.
    # The requester sees their service move from pending → accepted → completed.
    #
    # Frontend usage:
    #   subscription ServiceUpdates($serviceId: String!) {
    #     serviceStatusUpdates(serviceId: $serviceId) {
    #       id status updatedAt provider { username }
    #     }
    #   }

    @strawberry.subscription
    async def service_status_updates(
        self,
        info: Info,
        service_id: str,
    ) -> AsyncGenerator[ServiceRequestType, None]:
        """
        Push service status changes to the requester in real time.
        Listens on group: service_{service_id}
        """
        group_name = f'service_{service_id}'

        await channel_layer.group_add(group_name, info.context.ws.channel_name)

        try:
            while True:
                message = await channel_layer.receive(info.context.ws.channel_name)

                if message.get('type') == 'service_status_update':
                    payload = message['payload']
                    try:
                        service = await sync_to_async(
                            ServiceRequest.objects.select_related('requester', 'provider').get
                        )(id=payload['service_id'])
                        yield service
                    except ServiceRequest.DoesNotExist:
                        continue

        finally:
            await channel_layer.group_discard(group_name, info.context.ws.channel_name)