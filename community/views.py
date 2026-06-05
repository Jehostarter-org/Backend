from rest_framework import generics, permissions, status, filters
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.text import slugify
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_community_admin(user, community_id):
    """Return True if user has admin or moderator role in the community."""
    return CommunityMember.objects.filter(
        community_id=community_id,
        user=user,
        role__in=['admin', 'moderator'],
        is_banned=False,
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
        user = self.request.user
        if user.is_authenticated:
            membership = CommunityMember.objects.filter(
                community_id=OuterRef('pk'),
                user=user,
                is_banned=False,
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
        CommunityMember.objects.create(community=community, user=user, role='admin')
        Community.objects.filter(pk=community.pk).update(member_count=1)


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
        ).values_list('community_id', flat=True)

        admin_membership = CommunityMember.objects.filter(
            community_id=OuterRef('pk'),
            user=user,
            role__in=['admin', 'moderator'],
            is_banned=False,
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


class JoinCommunityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            community = Community.objects.get(pk=pk, is_active=True)
        except Community.DoesNotExist:
            return Response({'detail': 'Community not found.'}, status=404)
        member, created = CommunityMember.objects.get_or_create(community=community, user=request.user)
        if not created:
            return Response({'detail': 'Already a member.'}, status=400)
        # FIX: update member_count after a new member joins
        Community.objects.filter(pk=pk).update(
            member_count=CommunityMember.objects.filter(community_id=pk).count()
        )
        return Response({'detail': 'Joined community.'})


class LeaveCommunityView(APIView):
    def delete(self, request, pk):
        CommunityMember.objects.filter(community_id=pk, user=request.user).delete()
        # Keep member_count in sync on leave
        Community.objects.filter(pk=pk).update(
            member_count=CommunityMember.objects.filter(community_id=pk).count()
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommunityMembersView(generics.ListAPIView):
    serializer_class = CommunityMemberSerializer

    def get_queryset(self):
        return CommunityMember.objects.filter(
            community_id=self.kwargs['pk']
        ).select_related('user')


# ── Post views ────────────────────────────────────────────────────────────────

class PostListCreateView(generics.ListCreateAPIView):
    serializer_class = PostSerializer

    def get_queryset(self):
        return Post.objects.filter(community_id=self.kwargs['pk'], is_approved=True, is_deleted=False)

    def perform_create(self, serializer):
        community = Community.objects.get(pk=self.kwargs['pk'])
        if not community.members.filter(user=self.request.user).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You must be a member to post.')
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
        joined = CommunityMember.objects.filter(user=user).values_list('community_id', flat=True)
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
        ).exists()
        if not is_member:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You must be a member to access messages.')

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
        # Update member count
        Community.objects.filter(pk=pk).update(
            member_count=CommunityMember.objects.filter(community_id=pk).count()
        )
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
        member, created = CommunityMember.objects.get_or_create(
            community=community,
            user=request.user,
        )

        if not created:
            return Response({'detail': 'You are already a member of this community.'}, status=400)

        # Mark invite as used
        invite.used    = True
        invite.used_at = timezone.now()
        invite.save(update_fields=['used', 'used_at'])

        # Update member count
        Community.objects.filter(pk=community.pk).update(
            member_count=CommunityMember.objects.filter(community=community).count()
        )

        return Response({
            'detail':       'You have successfully joined the community.',
            'community_id': community.pk,
        })