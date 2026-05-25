from django.urls import path
from .views import (
    CommunityListCreateView, CommunityDetailView,
    JoinCommunityView, LeaveCommunityView, CommunityMembersView,
    PostListCreateView, PostDetailView, LikePostView,
    CommentListCreateView, ReportPostView, MyCommunityFeedView,
    CommunityMessageHistoryView,
)

urlpatterns = [
    path('',                         CommunityListCreateView.as_view(),     name='communities'),
    path('feed/',                    MyCommunityFeedView.as_view(),         name='community_feed'),
    path('<str:pk>/messages/',       CommunityMessageHistoryView.as_view(), name='community_messages'),
    path('<str:pk>/',                CommunityDetailView.as_view(),         name='community_detail'),
    path('<str:pk>/join/',           JoinCommunityView.as_view(),           name='join_community'),
    path('<str:pk>/leave/',          LeaveCommunityView.as_view(),          name='leave_community'),
    path('<str:pk>/members/',        CommunityMembersView.as_view(),        name='community_members'),
    path('<str:pk>/posts/',          PostListCreateView.as_view(),          name='community_posts'),
    path('posts/<str:pk>/',          PostDetailView.as_view(),              name='post_detail'),
    path('posts/<str:pk>/like/',     LikePostView.as_view(),                name='like_post'),
    path('posts/<str:pk>/comments/', CommentListCreateView.as_view(),       name='post_comments'),
    path('posts/<str:pk>/report/',   ReportPostView.as_view(),              name='report_post'),
]