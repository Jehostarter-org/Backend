"""
schema/mutations.py
"""

import strawberry
from strawberry.types import Info
from typing import Optional
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from datetime import datetime, timezone
from django.conf import settings
import logging

from .types import (
    UserType,
    PostType,
    CommentType,
    NotificationType,
    ServiceRequestType,
    CreatePostInput,
    CreateCommentInput,
    UpdateServiceStatusInput,
)
from community.models import Community, Post, Comment, PostLike, CommunityMember
from notifications.models import Notification
from services.models import ServiceRequest
from django.contrib.auth import get_user_model

User = get_user_model()
channel_layer = get_channel_layer()


def _broadcast(group: str, event_type: str, payload: dict):
    # Send a message to all WebSocket clients subscribed to a group
    async_to_sync(channel_layer.group_send)(
        group,
        {'type': event_type, 'payload': payload},
    )


# ── Input types ───────────────────────────────────────────────────────────────


@strawberry.input
class UpdateProfileInput:
    first_name:          Optional[str] = None
    last_name:           Optional[str] = None
    phone:               Optional[str] = None
    bio:                 Optional[str] = None
    current_country:     Optional[str] = None
    destination_country: Optional[str] = None
    city:                Optional[str] = None
    state_province:      Optional[str] = None
    migration_status:    Optional[str] = None


# ── Mutations ─────────────────────────────────────────────────────────────────

@strawberry.type
class Mutation:

    # ── Profile ───────────────────────────────────────────────────────────────

    @strawberry.mutation
    def update_profile(self, info: Info, input: UpdateProfileInput) -> UserType:
        """
        Update the logged-in user's profile.
        Avatar upload stays in DRF at /api/users/avatar/ since it's a file.
        Only fields that are actually passed get updated.
        """
        user = info.context.request.user

        if input.first_name is not None:
            user.first_name = input.first_name
        if input.last_name is not None:
            user.last_name = input.last_name
        if input.phone is not None:
            user.phone = input.phone
        if input.bio is not None:
            user.bio = input.bio
        if input.city is not None:
            user.city = input.city
        if input.state_province is not None:
            user.state_province = input.state_province
        if input.migration_status is not None:
            user.migration_status = input.migration_status

        if input.current_country is not None:
            if input.current_country not in settings.SUPPORTED_COUNTRIES:
                raise ValueError(f'{input.current_country} is not a supported country.')
            user.current_country = input.current_country

        if input.destination_country is not None:
            if input.destination_country not in settings.SUPPORTED_COUNTRIES:
                raise ValueError(f'{input.destination_country} is not a supported country.')
            user.destination_country = input.destination_country

        user.save()
        return user

    # ── Posts ─────────────────────────────────────────────────────────────────

    @strawberry.mutation
    def create_post(self, info: Info, input: CreatePostInput) -> PostType:
        """
        Create a new post in a community.
        Broadcasts to all subscribers of that community's feed in real time.
        """
        user = info.context.request.user
        community = Community.objects.get(id=input.community_id)

        post = Post.objects.create(
            community=community,
            author=user,
            post_type=input.post_type,
            content=input.content,
            video_url=input.video_url,
            video_title=input.video_title,
        )

        Community.objects.filter(id=community.id).update(
            post_count=community.post_count + 1
        )

        _broadcast(
            group=f'community_feed_{community.id}',
            event_type='new_post',
            payload={
                'post_id': post.id,
                'author': user.username,
                'post_type': post.post_type,
                'content': post.content[:200],
                'created_at': post.created_at.isoformat(),
            }
        )

        return post

    @strawberry.mutation
    def delete_post(self, info: Info, post_id: str) -> bool:
        """
        Soft-delete a post.
        Only the original author or a community admin/moderator can do this.
        """
        user = info.context.request.user

        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return False

        is_admin = CommunityMember.objects.filter(
            community=post.community,
            user=user,
            role__in=['admin', 'moderator'],
        ).exists()

        if post.author != user and not is_admin:
            raise PermissionError("You don't have permission to delete this post.")

        post.is_deleted = True
        post.deleted_by = user
        post.deleted_at = datetime.now(timezone.utc)
        post.save()

        return True

    # ── Comments ──────────────────────────────────────────────────────────────

    @strawberry.mutation
    def create_comment(self, info: Info, input: CreateCommentInput) -> CommentType:
        """
        Comment on a post. Supports threaded replies via parent_id.
        Notifies the post author in real time unless they're commenting on their own post.
        """
        user = info.context.request.user
        post = Post.objects.select_related('author').get(id=input.post_id)

        parent = None
        if input.parent_id:
            parent = Comment.objects.get(id=input.parent_id)

        comment = Comment.objects.create(
            post=post,
            author=user,
            content=input.content,
            parent=parent,
        )

        Post.objects.filter(id=post.id).update(
            comment_count=post.comment_count + 1
        )

        if post.author != user:
            notif = Notification.objects.create(
                recipient=post.author,
                actor=user,
                notification_type='comment',
                title=f'{user.username} commented on your post',
                message=input.content[:100],
                link=f'/community/post/{post.id}',
            )
            _broadcast(
                group=f'user_notifications_{post.author.id}',
                event_type='new_notification',
                payload={
                    'notification_id': notif.id,
                    'type': notif.notification_type,
                    'title': notif.title,
                    'message': notif.message,
                    'created_at': notif.created_at.isoformat(),
                }
            )

        return comment

    # ── Likes ─────────────────────────────────────────────────────────────────

    @strawberry.mutation
    def toggle_like(self, info: Info, post_id: str) -> bool:
        """
        Like or unlike a post.
        Returns True if the post is now liked, False if it was unliked.
        Notifies the post author when someone likes their post.
        """
        user = info.context.request.user
        post = Post.objects.select_related('author').get(id=post_id)

        like, created = PostLike.objects.get_or_create(post=post, user=user)

        if created:
            Post.objects.filter(id=post.id).update(like_count=post.like_count + 1)

            if post.author != user:
                notif = Notification.objects.create(
                    recipient=post.author,
                    actor=user,
                    notification_type='like',
                    title=f'{user.username} liked your post',
                    message=post.content[:80],
                    link=f'/community/post/{post.id}',
                )
                _broadcast(
                    group=f'user_notifications_{post.author.id}',
                    event_type='new_notification',
                    payload={
                        'notification_id': notif.id,
                        'type': notif.notification_type,
                        'title': notif.title,
                        'message': notif.message,
                        'created_at': notif.created_at.isoformat(),
                    }
                )
            return True
        else:
            like.delete()
            Post.objects.filter(id=post.id).update(
                like_count=max(post.like_count - 1, 0)
            )
            return False

    # ── Notifications ─────────────────────────────────────────────────────────

    @strawberry.mutation
    def mark_notification_read(self, info: Info, notification_id: str) -> bool:
        user = info.context.request.user
        updated = Notification.objects.filter(
            id=notification_id,
            recipient=user,
        ).update(is_read=True, read_at=datetime.now(timezone.utc))
        return updated > 0

    @strawberry.mutation
    def mark_all_notifications_read(self, info: Info) -> int:
        user = info.context.request.user
        return Notification.objects.filter(
            recipient=user,
            is_read=False,
        ).update(is_read=True, read_at=datetime.now(timezone.utc))

    # ── Services ──────────────────────────────────────────────────────────────

    @strawberry.mutation
    def update_service_status(
        self, info: Info, input: UpdateServiceStatusInput
    ) -> ServiceRequestType:
        """
        Provider updates the status of a service request.
        Notifies the requester in real time and broadcasts a status update
        to anyone watching that specific service.
        """
        user = info.context.request.user
        service = ServiceRequest.objects.select_related(
            'requester', 'provider'
        ).get(id=input.service_request_id)

        if service.provider != user:
            raise PermissionError("Only the assigned provider can update this service.")

        service.status = input.status
        if input.notes:
            service.notes = input.notes
        service.save()

        notif_type_map = {
            'accepted':    'service_accepted',
            'in_progress': 'service_updated',
            'completed':   'service_completed',
            'cancelled':   'service_cancelled',
        }

        notif = Notification.objects.create(
            recipient=service.requester,
            actor=user,
            notification_type=notif_type_map.get(input.status, 'service_updated'),
            title=f'Your {service.get_service_type_display()} is {input.status}',
            message=input.notes or f'Status updated to {input.status}',
            link=f'/services/{service.id}',
        )

        _broadcast(
            group=f'user_notifications_{service.requester.id}',
            event_type='new_notification',
            payload={
                'notification_id': notif.id,
                'type': notif.notification_type,
                'title': notif.title,
                'message': notif.message,
                'created_at': notif.created_at.isoformat(),
            }
        )

        _broadcast(
            group=f'service_{service.id}',
            event_type='service_status_update',
            payload={
                'service_id': service.id,
                'status': service.status,
                'updated_at': service.updated_at.isoformat(),
            }
        )

        return service