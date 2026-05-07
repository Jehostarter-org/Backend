 
from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.text import slugify
import uuid
from .models import Community, CommunityMember, Post, Comment, PostLike, PostReport
from .serializers import (
    CommunitySerializer, CommunityMemberSerializer,
    PostSerializer, CommentSerializer, PostReportSerializer,
)


class CommunityListCreateView(generics.ListCreateAPIView):
    serializer_class = CommunitySerializer
    filter_backends  = [filters.SearchFilter]
    search_fields    = ['name', 'description', 'country_code']

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
        CommunityMember.objects.create(community=community, user=user, role='admin')


class CommunityDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = Community.objects.all()
    serializer_class   = CommunitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


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
        return CommunityMember.objects.filter(community_id=self.kwargs['pk'])


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
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


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
        user     = self.request.user
        joined   = CommunityMember.objects.filter(user=user).values_list('community_id', flat=True)
        return Post.objects.filter(community_id__in=joined, is_approved=True, is_deleted=False)