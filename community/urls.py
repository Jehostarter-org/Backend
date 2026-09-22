from django.urls import path
from .views import (
    CommunityListCreateView, MyCommunitiesListView, CommunityDetailView,
    JoinCommunityView, LeaveCommunityView, CommunityMembersView,
    PendingMembersView, ApproveMemberView, RejectMemberView,
    RemoveMemberView, AdminCommunityMembershipListView,
    GenerateInviteLinkView, InviteByEmailView, AcceptInviteView,
    PostListCreateView, PostDetailView, LikePostView,
    CommentListCreateView, ReportPostView, MyCommunityFeedView,
    CommunityMessageHistoryView, CommunityLiveActivityView, DeleteMessageView, ToggleReactionView,
    ShareListingToGroupsView,
)

urlpatterns = [
    path('',                         CommunityListCreateView.as_view(),     name='communities'),
    path('mine/',                    MyCommunitiesListView.as_view(),       name='my_communities'),
    path('feed/',                    MyCommunityFeedView.as_view(),         name='community_feed'),

    # ── Super-admin portal (staff only) ──────────────────────────────────────
    path('admin/memberships/',       AdminCommunityMembershipListView.as_view(), name='admin_community_memberships'),

    # ── Invite (no community PK prefix — token is globally unique) ───────────
    path('invite/<str:token>/accept/', AcceptInviteView.as_view(),          name='accept_invite'),

    # ── Messages ──────────────────────────────────────────────────────────────
    path('messages/activity/',     CommunityLiveActivityView.as_view(),   name='community_live_activity'),
    path('<str:pk>/messages/',       CommunityMessageHistoryView.as_view(), name='community_messages'),
    path('<str:community_pk>/messages/<str:message_pk>/delete/',
         DeleteMessageView.as_view(), name='delete_community_message'),
    path('<str:community_pk>/messages/<str:message_pk>/react/',
         ToggleReactionView.as_view(), name='toggle_reaction'),

    # ── Member actions ────────────────────────────────────────────────────────
    path('<str:pk>/join/',           JoinCommunityView.as_view(),           name='join_community'),
    path('<str:pk>/leave/',          LeaveCommunityView.as_view(),          name='leave_community'),
    path('<str:pk>/members/',        CommunityMembersView.as_view(),        name='community_members'),
    path('<str:pk>/members/pending/', PendingMembersView.as_view(),         name='pending_members'),
    path('<str:pk>/members/<str:member_pk>/approve/', ApproveMemberView.as_view(), name='approve_member'),
    path('<str:pk>/members/<str:member_pk>/reject/',  RejectMemberView.as_view(),  name='reject_member'),
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

    # ── Shop listing sharing ───────────────────────────────────────────────────
    path('share-listing/',           ShareListingToGroupsView.as_view(),   name='share_listing'),

    # ── Community CRUD — MUST be last (greedy <str:pk>/ catch-all) ───────────
    path('<str:pk>/',                CommunityDetailView.as_view(),         name='community_detail'),
]