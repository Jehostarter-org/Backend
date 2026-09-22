from rest_framework import generics, permissions, status, filters
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.text import slugify
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Coalesce
import uuid
from .models import Community, CommunityMember, Post, Comment, PostLike, PostReport, Message
from .message_notifications import notify_community_members
from .serializers import (
    CommunitySerializer, CommunityMemberSerializer,
    PostSerializer, CommentSerializer, PostReportSerializer, MessageSerializer,
)
from django.contrib.auth import get_user_model
import secrets
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings as django_settings
from .models import CommunityInvite
from .broadcast import broadcast_to_community, broadcast_global_event, broadcast_to_user
from shops.models import ShopListing


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_community_admin(user, community_id):
    """Return True if user has admin or moderator role in the community (approved only)."""
    return CommunityMember.objects.filter(
        community_id=community_id,
        user=user,
        role__in=['admin', 'moderator'],
        is_banned=False,
        status='approved',
    ).exists()


# ── Permissions ───────────────────────────────────────────────────────────────

class IsCommunityAdminOrReadOnly(permissions.BasePermission):
    """
    Safe methods are always allowed.
    Write methods require the requesting user to hold admin/moderator role
    in the community's CommunityMember table.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return _is_community_admin(request.user, obj.pk)


class IsPostAuthorOrCommunityAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if obj.author == request.user:
            return True
        return _is_community_admin(request.user, obj.community_id)


# ── Community views ───────────────────────────────────────────────────────────

class CommunityListCreateView(generics.ListCreateAPIView):
    serializer_class = CommunitySerializer
    filter_backends  = [filters.SearchFilter]
    search_fields    = ['name', 'description', 'country_code']
    parser_classes   = [MultiPartParser, FormParser, JSONParser]
    pagination_class = None  # return full list — paginated page 1 hid new groups after refresh

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    def get_queryset(self):
        qs = (
            Community.objects
            .filter(is_active=True)
            .select_related('creator')
            .prefetch_related('members')
        )
        country = (self.request.query_params.get('country') or '').strip().upper()
        if country:
            qs = qs.filter(country_code=country)
        user = self.request.user
        if user.is_authenticated:
            membership = CommunityMember.objects.filter(
                community_id=OuterRef('pk'),
                user=user,
                is_banned=False,
                status='approved',
            )
            qs = qs.annotate(
                _is_member=Exists(membership),
                _is_admin=Exists(
                    membership.filter(role__in=['admin', 'moderator'])
                ),
            )
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        user      = self.request.user
        name      = serializer.validated_data['name']
        slug      = slugify(name) + '-' + str(uuid.uuid4())[:8]
        community = serializer.save(creator=user, slug=slug, country_code=user.current_country or '', is_active=True)
        CommunityMember.objects.create(community=community, user=user, role='admin', approved_at=timezone.now())
        Community.objects.filter(pk=community.pk).update(member_count=1)

        # Broadcast to all connected clients
        data = CommunitySerializer(community, context={'request': self.request}).data
        broadcast_global_event('community_created', {'community': data})


class MyCommunitiesListView(generics.ListAPIView):
    """
    GET /api/community/mine/ — communities the user created or joined.
    Used for the Groups tab so created communities always appear after refresh.
    """
    serializer_class   = CommunitySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        user = self.request.user
        member_ids = CommunityMember.objects.filter(
            user=user,
            is_banned=False,
            status='approved',
        ).values_list('community_id', flat=True)

        admin_membership = CommunityMember.objects.filter(
            community_id=OuterRef('pk'),
            user=user,
            role__in=['admin', 'moderator'],
            is_banned=False,
            status='approved',
        )
        return (
            Community.objects
            .filter(is_active=True)
            .filter(Q(id__in=member_ids) | Q(creator=user))
            .distinct()
            .select_related('creator')
            .prefetch_related('members')
            .annotate(_is_admin=Exists(admin_membership))
        )

    def create(self, request, *args, **kwargs):
        """Return full community payload with is_member/is_admin after membership row exists."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        output = CommunitySerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


class CommunityDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    PATCH /community/<pk>/  — admin/moderator only (cover_image upload works here).
    Accepts multipart/form-data so the frontend can send a FormData with cover_image.
    """
    queryset           = Community.objects.all()
    serializer_class   = CommunitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsCommunityAdminOrReadOnly]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def perform_update(self, serializer):
        super().perform_update(serializer)
        data = CommunitySerializer(serializer.instance, context={'request': self.request}).data
        broadcast_to_community(str(serializer.instance.pk), 'community_updated', {'community': data})
        broadcast_global_event('community_updated', {'community': data})

    def perform_destroy(self, instance):
        community_id = str(instance.pk)
        super().perform_destroy(instance)
        broadcast_to_community(community_id, 'community_deleted', {'community_id': community_id})
        broadcast_global_event('community_deleted', {'community_id': community_id})


class JoinCommunityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            community = Community.objects.get(pk=pk, is_active=True)
        except Community.DoesNotExist:
            return Response({'detail': 'Community not found.'}, status=404)

        existing = CommunityMember.objects.filter(community=community, user=request.user).first()
        if existing:
            if existing.status == 'pending':
                return Response({'detail': 'Request already pending.'}, status=400)
            if existing.is_banned:
                return Response({'detail': 'You are banned from this community.'}, status=403)
            return Response({'detail': 'Already a member.'}, status=400)

        if community.require_approval:
            member = CommunityMember.objects.create(
                community=community, user=request.user, status='pending',
            )
            # notify admins
            admin_ids = CommunityMember.objects.filter(
                community=community, role__in=['admin', 'moderator'], is_banned=False,
            ).values_list('user_id', flat=True)
            for uid in admin_ids:
                broadcast_to_user(str(uid), 'join_request', {
                    'community_id': str(community.pk),
                    'community_name': community.name,
                    'user_id': str(request.user.pk),
                    'username': request.user.username,
                })
            return Response({'detail': 'Request sent. Waiting for admin approval.', 'status': 'pending'})

        member = CommunityMember.objects.create(community=community, user=request.user, status='approved', approved_at=timezone.now())
        member_count = CommunityMember.objects.filter(community_id=pk, status='approved').count()
        Community.objects.filter(pk=pk).update(member_count=member_count)

        avatar_url = None
        try:
            avatar_field = getattr(request.user, 'avatar', None) or getattr(request.user, 'profile_picture', None)
            if avatar_field:
                avatar_url = avatar_field.url
        except Exception:
            pass
        broadcast_to_community(str(pk), 'member_joined', {
            'user_id': str(request.user.pk),
            'username': request.user.username,
            'avatar': avatar_url,
            'member_count': member_count,
        })

        return Response({'detail': 'Joined community.'})


class LeaveCommunityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        CommunityMember.objects.filter(community_id=pk, user=request.user).delete()
        member_count = CommunityMember.objects.filter(community_id=pk).count()
        Community.objects.filter(pk=pk).update(member_count=member_count)
        broadcast_to_community(str(pk), 'member_left', {
            'user_id': str(request.user.pk),
            'username': request.user.username,
            'member_count': member_count,
        })
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommunityMembersView(generics.ListAPIView):
    serializer_class = CommunityMemberSerializer

    def get_queryset(self):
        return CommunityMember.objects.filter(
            community_id=self.kwargs['pk'], status='approved',
        ).select_related('user')


class PendingMembersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        if not _is_community_admin(request.user, pk):
            return Response({'detail': 'Admin access required.'}, status=403)
        members = CommunityMember.objects.filter(
            community_id=pk, status='pending',
        ).select_related('user')
        data = []
        for m in members:
            avatar_url = None
            try:
                av = getattr(m.user, 'avatar', None) or getattr(m.user, 'profile_picture', None)
                if av and av.storage.exists(av.name):
                    avatar_url = request.build_absolute_uri(av.url)
            except Exception:
                pass
            data.append({
                'id': m.id,
                'user_id': str(m.user.pk),
                'username': m.user.username,
                'profile_picture': avatar_url,
                'requested_at': m.joined_at.isoformat(),
            })
        return Response(data)


class ApproveMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, member_pk):
        if not _is_community_admin(request.user, pk):
            return Response({'detail': 'Admin access required.'}, status=403)
        try:
            member = CommunityMember.objects.get(pk=member_pk, community_id=pk, status='pending')
        except CommunityMember.DoesNotExist:
            return Response({'detail': 'Pending request not found.'}, status=404)
        member.status = 'approved'
        member.approved_at = timezone.now()
        member.save(update_fields=['status', 'approved_at'])

        member_count = CommunityMember.objects.filter(community_id=pk, status='approved').count()
        Community.objects.filter(pk=pk).update(member_count=member_count)

        broadcast_to_community(str(pk), 'member_joined', {
            'user_id': str(member.user_id),
            'username': member.user.username,
            'member_count': member_count,
        })
        broadcast_to_user(str(member.user_id), 'join_approved', {
            'community_id': str(pk),
            'community_name': Community.objects.get(pk=pk).name,
        })
        return Response({'detail': 'Member approved.'})


class RejectMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, member_pk):
        if not _is_community_admin(request.user, pk):
            return Response({'detail': 'Admin access required.'}, status=403)
        try:
            member = CommunityMember.objects.get(pk=member_pk, community_id=pk, status='pending')
        except CommunityMember.DoesNotExist:
            return Response({'detail': 'Pending request not found.'}, status=404)
        member.status = 'rejected'
        member.save(update_fields=['status'])
        broadcast_to_user(str(member.user_id), 'join_rejected', {
            'community_id': str(pk),
            'community_name': Community.objects.get(pk=pk).name,
        })
        return Response({'detail': 'Request rejected.'})


class AdminCommunityMembershipListView(APIView):
    """
    GET /api/community/admin/memberships/ — staff only.
    Live view of approved community memberships for the super-admin portal,
    including when each person was accepted into the group (approved_at).
    """
    permission_classes = [permissions.IsAdminUser]
    pagination_class   = None

    def get(self, request):
        members = (
            CommunityMember.objects
            .filter(status='approved')
            .select_related('user', 'community')
            .annotate(accepted_at=Coalesce('approved_at', 'joined_at'))
            .order_by('-accepted_at')
        )
        data = []
        for m in members:
            data.append({
                'id':             m.id,
                'community_id':   str(m.community_id),
                'community_name': m.community.name,
                'user_id':        str(m.user_id),
                'username':       m.user.username,
                'email':          m.user.email or '',
                'role':           m.role,
                'status':         m.status,
                'requested_at':   m.joined_at.isoformat(),
                'approved_at':    m.approved_at.isoformat() if m.approved_at else None,
            })
        return Response(data)


# ── Post views ────────────────────────────────────────────────────────────────

class PostListCreateView(generics.ListCreateAPIView):
    serializer_class = PostSerializer

    def get_queryset(self):
        return Post.objects.filter(community_id=self.kwargs['pk'], is_approved=True, is_deleted=False)

    def perform_create(self, serializer):
        community = Community.objects.get(pk=self.kwargs['pk'])
        if not community.members.filter(user=self.request.user, status='approved', is_banned=False).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You must be an approved member to post.')
        serializer.save(author=self.request.user, community=community)


class PostDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = Post.objects.all()
    serializer_class   = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsPostAuthorOrCommunityAdminOrReadOnly]


class LikePostView(APIView):
    def post(self, request, pk):
        try:
            post = Post.objects.get(pk=pk)
        except Post.DoesNotExist:
            return Response({'detail': 'Post not found.'}, status=404)
        like, created = PostLike.objects.get_or_create(post=post, user=request.user)
        if not created:
            like.delete()
            return Response({'liked': False})
        return Response({'liked': True})


class CommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.filter(post_id=self.kwargs['pk'], parent=None, is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, post_id=self.kwargs['pk'])


class ReportPostView(generics.CreateAPIView):
    serializer_class = PostReportSerializer

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user, post_id=self.kwargs['pk'])


class MyCommunityFeedView(generics.ListAPIView):
    serializer_class = PostSerializer

    def get_queryset(self):
        user   = self.request.user
        joined = CommunityMember.objects.filter(user=user, status='approved', is_banned=False).values_list('community_id', flat=True)
        return Post.objects.filter(community_id__in=joined, is_approved=True, is_deleted=False)


# ── Message views ─────────────────────────────────────────────────────────────

class CommunityMessageHistoryView(generics.ListCreateAPIView):
    """
    GET  /api/community/<pk>/messages/  — last 50 messages, oldest-first (members only)
    POST /api/community/<pk>/messages/  — send a message with optional file attachment
    """
    serializer_class   = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def _assert_member(self, community_id):
        is_member = CommunityMember.objects.filter(
            community_id=community_id,
            user=self.request.user,
            is_banned=False,
            status='approved',
        ).exists()
        if not is_member:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You must be an approved member to access messages.')

    def get_queryset(self):
        community_id = self.kwargs['pk']
        self._assert_member(community_id)
        return (
            Message.objects
            .filter(community_id=community_id, is_deleted=False)
            .select_related('sender', 'reply_to__sender')
            .order_by('-created_at')[:50]
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(reversed(list(qs)), many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        community_id = self.kwargs['pk']
        self._assert_member(community_id)
        attachment = self.request.FILES.get('attachment')
        message = serializer.save(
            sender=self.request.user,
            community_id=community_id,
            attachment_name=getattr(attachment, 'name', '') if attachment else '',
            attachment_type=getattr(attachment, 'content_type', '') if attachment else '',
            attachment_size=getattr(attachment, 'size', 0) if attachment else 0,
        )
        notify_community_members(message)


class CommunityLiveActivityView(generics.ListAPIView):
    """
    GET /api/community/messages/activity/ — latest chat messages across all
    communities the user belongs to, newest-first. Powers the dashboard
    "Community Live Activity" widget.
    """
    serializer_class   = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user   = self.request.user
        joined = CommunityMember.objects.filter(
            user=user, status='approved', is_banned=False
        ).values_list('community_id', flat=True)
        return (
            Message.objects
            .filter(community_id__in=joined, is_deleted=False)
            .select_related('sender')
            .order_by('-created_at')[:30]
        )


class DeleteMessageView(APIView):
    """
    DELETE /api/community/<community_pk>/messages/<message_pk>/delete/

    Rules
    -----
    • A user may delete their own messages.
    • A community admin or moderator may delete any message.
    • Deletion is a soft-delete (is_deleted=True) so history is auditable.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, community_pk, message_pk):
        try:
            message = Message.objects.select_related('community').get(
                pk=message_pk,
                community_id=community_pk,
                is_deleted=False,
            )
        except Message.DoesNotExist:
            return Response({'detail': 'Message not found.'}, status=404)

        is_own_message = message.sender_id == request.user.pk
        is_admin       = _is_community_admin(request.user, community_pk)

        if not (is_own_message or is_admin):
            return Response(
                {'detail': 'You do not have permission to delete this message.'},
                status=403,
            )

        message.is_deleted = True
        message.save(update_fields=['is_deleted'])
        return Response(status=status.HTTP_204_NO_CONTENT)

class ToggleReactionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, community_pk, message_pk):
        try:
            message = Message.objects.get(
                pk=message_pk,
                community_id=community_pk,
                is_deleted=False,
            )
        except Message.DoesNotExist:
            return Response({'detail': 'Message not found.'}, status=404)

        emoji = request.data.get('emoji', '').strip()
        if not emoji:
            return Response({'detail': 'Emoji is required.'}, status=400)

        user_id = str(request.user.pk)
        reactions = dict(message.reactions or {})
        users = reactions.get(emoji, [])

        if user_id in users:
            users.remove(user_id)
            if not users:
                reactions.pop(emoji, None)
            else:
                reactions[emoji] = users
            message.reactions = reactions
            message.save(update_fields=['reactions'])
        else:
            reactions.setdefault(emoji, []).append(user_id)
            message.reactions = reactions
            message.save(update_fields=['reactions'])

        broadcast_to_community(str(community_pk), 'reaction_toggled', {
            'message_id': str(message_pk),
            'reactions': message.reactions,
        })

        return Response({'reactions': message.reactions})

class RemoveMemberView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, user_pk):
        if not _is_community_admin(request.user, pk):
            return Response({'detail': 'Admin access required.'}, status=403)
        deleted, _ = CommunityMember.objects.filter(
            community_id=pk, user_id=user_pk
        ).delete()
        if not deleted:
            return Response({'detail': 'Member not found.'}, status=404)
        member_count = CommunityMember.objects.filter(community_id=pk).count()
        Community.objects.filter(pk=pk).update(member_count=member_count)
        broadcast_to_community(str(pk), 'member_removed', {
            'user_id': str(user_pk),
            'removed_by': str(request.user.pk),
            'member_count': member_count,
        })
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateInviteLinkView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_community_admin(request.user, pk):
            return Response({'detail': 'Admin access required.'}, status=403)
        try:
            community = Community.objects.get(pk=pk)
        except Community.DoesNotExist:
            return Response({'detail': 'Community not found.'}, status=404)

        token      = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(days=7)

        invite = CommunityInvite.objects.create(
            community=community,
            invited_by=request.user,
            token=token,
            expires_at=expires_at,
        )

        frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')
        invite_url   = f"{frontend_url}/invite/{invite.token}"

        return Response({
            'invite_url': invite_url,
            'token':      invite.token,
            'expires_at': invite.expires_at.isoformat(),
        })


class InviteByEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_community_admin(request.user, pk):
            return Response({'detail': 'Admin access required.'}, status=403)
        try:
            community = Community.objects.get(pk=pk)
        except Community.DoesNotExist:
            return Response({'detail': 'Community not found.'}, status=404)

        emails = request.data.get('emails', [])
        if not emails:
            return Response({'detail': 'No emails provided.'}, status=400)

        User         = get_user_model()
        frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')
        sent         = []
        skipped      = []

        for email in emails:
            email = email.strip().lower()
            if not email:
                continue

            # Check if user exists in the platform
            if not User.objects.filter(email=email).exists():
                skipped.append(email)
                continue

            # Skip if already a member
            user = User.objects.get(email=email)
            if CommunityMember.objects.filter(community=community, user=user).exists():
                skipped.append(email)
                continue

            token      = secrets.token_urlsafe(32)
            expires_at = timezone.now() + timedelta(days=7)

            invite = CommunityInvite.objects.create(
                community=community,
                invited_by=request.user,
                email=email,
                token=token,
                expires_at=expires_at,
            )

            invite_url = f"{frontend_url}/invite/{invite.token}"

            send_mail(
                subject=f"You've been invited to join {community.name}",
                message=(
                    f"Hi,\n\n"
                    f"{request.user.username} has invited you to join "
                    f"'{community.name}' on the platform.\n\n"
                    f"Click the link below to accept:\n{invite_url}\n\n"
                    f"This link expires in 7 days."
                ),
                from_email=getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=[email],
                fail_silently=True,
            )
            sent.append(email)

        return Response({
            'sent':    sent,
            'skipped': skipped,
            'detail':  f"Invites sent to {len(sent)} user(s). {len(skipped)} skipped.",
        })


class AcceptInviteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, token):
        try:
            invite = CommunityInvite.objects.select_related('community').get(
                token=token,
                used=False,
            )
        except CommunityInvite.DoesNotExist:
            return Response({'detail': 'Invalid or expired invite link.'}, status=404)

        if invite.expires_at < timezone.now():
            return Response({'detail': 'This invite link has expired.'}, status=410)

        community = invite.community

        existing = CommunityMember.objects.filter(community=community, user=request.user).first()
        if existing:
            if existing.status == 'pending':
                return Response({'detail': 'Your request is still pending approval.'}, status=400)
            return Response({'detail': 'You are already a member of this community.'}, status=400)

        if existing and existing.is_banned:
            return Response({'detail': 'You are banned from this community.'}, status=403)

        if community.require_approval:
            member = CommunityMember.objects.create(
                community=community, user=request.user, status='pending',
            )
            invite.used = True
            invite.used_at = timezone.now()
            invite.save(update_fields=['used', 'used_at'])
            return Response({
                'detail': 'Request sent. Waiting for admin approval.',
                'community_id': community.pk,
                'status': 'pending',
            })

        member = CommunityMember.objects.create(
            community=community, user=request.user, status='approved',
            approved_at=timezone.now(),
        )

        # Mark invite as used
        invite.used    = True
        invite.used_at = timezone.now()
        invite.save(update_fields=['used', 'used_at'])

        # Update member count
        member_count = CommunityMember.objects.filter(community=community, status='approved').count()
        Community.objects.filter(pk=community.pk).update(member_count=member_count)

        return Response({
            'detail':       'You have successfully joined the community.',
            'community_id': community.pk,
        })


class ShareListingToGroupsView(APIView):
    """
    POST /api/community/share-listing/
    Body: { "listing_id": "<str>", "community_ids": ["<str>", ...] }

    Creates a shop_promo Post in each listed community that the user belongs to.
    Skips communities where the user is not a member.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        listing_id   = request.data.get('listing_id')
        community_ids = request.data.get('community_ids', [])

        if not listing_id:
            return Response({'detail': 'listing_id is required.'}, status=400)
        if not community_ids:
            return Response({'detail': 'community_ids is required.'}, status=400)

        try:
            listing = ShopListing.objects.get(pk=listing_id)
        except ShopListing.DoesNotExist:
            return Response({'detail': 'Listing not found.'}, status=404)

        member_ids = set(
            CommunityMember.objects.filter(
                user=request.user,
                is_banned=False,
                status='approved',
            ).values_list('community_id', flat=True)
        )

        created = []
        skipped = []
        
        category_slug = listing.category.slug if listing.category else 'marketplace'
        slug_to_segment = {
            'marketplace': 'marketplace',
            'vehicles': 'vehicles',
            'housing': 'housing',
            'fashion': 'fashion',
            'electronics': 'electronics',
            'furniture': 'furniture',
            'baby-kids': 'baby-kids-store',
            'books': 'books',
            'equipment-tools': 'equipment-tools',
        }
        url_segment = slug_to_segment.get(category_slug, category_slug)
        frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        product_url = f"{frontend_url}/dashboard/product/{url_segment}?listing={listing.id}"
        
        for cid in community_ids:
            if cid not in member_ids:
                skipped.append(cid)
                continue
            
            # 1. Create shop promo Post
            post = Post.objects.create(
                community_id=cid,
                author=request.user,
                post_type='shop_promo',
                content=listing.title,
                shop_listing=listing,
            )
            created.append({'community_id': cid, 'post_id': post.pk})
            
            # 2. Create Chat Message so it appears in the community chat
            message_content = f"Shared a listing: {listing.title}\n{product_url}"
            message = Message.objects.create(
                community_id=cid,
                sender=request.user,
                content=message_content,
            )
            
            # 3. Notify other group members
            try:
                notify_community_members(message)
            except Exception as e:
                pass
            
            # 4. Broadcast to WS group
            avatar_url = None
            avatar = getattr(request.user, 'avatar', None) or getattr(request.user, 'profile_picture', None)
            if avatar:
                try:
                    avatar_url = request.build_absolute_uri(avatar.url)
                except Exception:
                    pass
            
            try:
                broadcast_to_community(
                    community_id=cid,
                    event_type='chat_message',
                    payload={
                        'id':              str(message.id),
                        'content':         message.content,
                        'sender_id':       str(request.user.id),
                        'sender_username': request.user.username,
                        'sender_avatar':   avatar_url,
                        'reply_to':        None,
                        'attachment_url':  None,
                        'attachment_name': '',
                        'attachment_type': '',
                        'attachment_size': 0,
                        'created_at':      message.created_at.isoformat(),
                    }
                )
            except Exception as e:
                pass

        return Response({
            'created': created,
            'skipped': skipped,
            'detail':  f"Shared to {len(created)} group(s). {len(skipped)} skipped.",
        })