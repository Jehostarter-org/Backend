from django.urls import path
from .views import (
    CommunityListCreateView, MyCommunitiesListView, CommunityDetailView,
    JoinCommunityView, LeaveCommunityView, CommunityMembersView,
    RemoveMemberView,
    GenerateInviteLinkView, InviteByEmailView, AcceptInviteView,
    PostListCreateView, PostDetailView, LikePostView,
    CommentListCreateView, ReportPostView, MyCommunityFeedView,
    CommunityMessageHistoryView, DeleteMessageView,
)

urlpatterns = [
    path('',                         CommunityListCreateView.as_view(),     name='communities'),
    path('mine/',                    MyCommunitiesListView.as_view(),       name='my_communities'),
    path('feed/',                    MyCommunityFeedView.as_view(),         name='community_feed'),

    # ── Invite (no community PK prefix — token is globally unique) ───────────
    path('invite/<str:token>/accept/', AcceptInviteView.as_view(),          name='accept_invite'),

    # ── Messages ──────────────────────────────────────────────────────────────
    path('<str:pk>/messages/',       CommunityMessageHistoryView.as_view(), name='community_messages'),
    path('<str:community_pk>/messages/<str:message_pk>/delete/',
         DeleteMessageView.as_view(), name='delete_community_message'),

    # ── Member actions ────────────────────────────────────────────────────────
    path('<str:pk>/join/',           JoinCommunityView.as_view(),           name='join_community'),
    path('<str:pk>/leave/',          LeaveCommunityView.as_view(),          name='leave_community'),
    path('<str:pk>/members/',        CommunityMembersView.as_view(),        name='community_members'),
    path('<str:pk>/members/<str:user_pk>/remove/',
         RemoveMemberView.as_view(),        name='remove_member'),

    # ── Admin actions ─────────────────────────────────────────────────────────
    path('<str:pk>/invite/link/',    GenerateInviteLinkView.as_view(),      name='invite_link'),
    path('<str:pk>/invite/email/',   InviteByEmailView.as_view(),           name='invite_email'),

    # ── Posts ─────────────────────────────────────────────────────────────────
    path('<str:pk>/posts/',          PostListCreateView.as_view(),          name='community_posts'),
    path('posts/<str:pk>/',          PostDetailView.as_view(),              name='post_detail'),
    path('posts/<str:pk>/like/',     LikePostView.as_view(),                name='like_post'),
    path('posts/<str:pk>/comments/', CommentListCreateView.as_view(),       name='post_comments'),
    path('posts/<str:pk>/report/',   ReportPostView.as_view(),              name='report_post'),

    # ── Community CRUD — MUST be last (greedy <str:pk>/ catch-all) ───────────
    path('<str:pk>/',                CommunityDetailView.as_view(),         name='community_detail'),
]