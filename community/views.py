from rest_framework import generics, permissions, status, filters
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.text import slugify
import uuid
from .models import Community, CommunityMember, Post, Comment, PostLike, PostReport, Message
from .serializers import (
    CommunitySerializer, CommunityMemberSerializer,
    PostSerializer, CommentSerializer, PostReportSerializer, MessageSerializer,
)


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

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    def get_queryset(self):
        return Community.objects.filter(is_active=True)

    def perform_create(self, serializer):
        user      = self.request.user
        name      = serializer.validated_data['name']
        slug      = slugify(name) + '-' + str(uuid.uuid4())[:8]
        community = serializer.save(creator=user, slug=slug, country_code=user.current_country)
        # Creator is always stored as admin in CommunityMember — this is the
        # source of truth for permission checks throughout the app.
        CommunityMember.objects.create(community=community, user=user, role='admin')


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
        return Response({'detail': 'Joined community.'})


class LeaveCommunityView(APIView):
    def delete(self, request, pk):
        CommunityMember.objects.filter(community_id=pk, user=request.user).delete()
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
            .select_related('sender')
            .order_by('-created_at')[:50]
        )[::-1]

    def perform_create(self, serializer):
        community_id = self.kwargs['pk']
        self._assert_member(community_id)
        attachment = self.request.FILES.get('attachment')
        serializer.save(
            sender=self.request.user,
            community_id=community_id,
            attachment_name=getattr(attachment, 'name', '') if attachment else '',
            attachment_type=getattr(attachment, 'content_type', '') if attachment else '',
            attachment_size=getattr(attachment, 'size', 0) if attachment else 0,
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