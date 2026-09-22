from django.urls import path
from .views import (
    CategoryListView, ShopCreateView, ShopDetailView, MyShopView,
    ShopListingListCreateView, MyShopListingsView, ShopListingDetailView,
    BoostListingView, BoostedListingsView, MySavedListingsView, BookmarkListingView,
    ShopCreateWithApprovalView,
    MyShopApprovalStatusView, UploadShopDocumentView, DeleteShopDocumentView,
    ResubmitShopApprovalView, AdminPendingApprovalsView,
    AdminAllShopApprovalsView, AdminShopApprovalDetailView,
    AdminProcessShopApprovalView, AdminReviewDocumentsView, AdminShopStatsView,
    AdminListingListView, AdminListingDeleteView,
)

urlpatterns = [
    # ── Categories ──────────────────────────────────────────────────────────
    path('categories/', CategoryListView.as_view(), name='categories'),

    # ── Shop CRUD (specific paths before <pk> catch-all) ─────────────────────
    path('create/', ShopCreateView.as_view(), name='shop_create'),
    path('create-with-approval/', ShopCreateWithApprovalView.as_view(), name='shop_create_with_approval'),
    path('my/', MyShopView.as_view(), name='my_shop'),
    path('my/approval-status/', MyShopApprovalStatusView.as_view(), name='my_shop_approval_status'),
    path('my/resubmit/', ResubmitShopApprovalView.as_view(), name='resubmit_shop_approval'),

    # ── Saved listings (buyer cart) ───────────────────────────────────────────
    path('saved/', MySavedListingsView.as_view(), name='saved_listings'),

    # ── Listings ─────────────────────────────────────────────────────────────
    # ORDERING RULES:
    #   1. Exact literals first  (listings/, listings/my/, boosted/)
    #   2. Paths with a pk segment AND a suffix before the bare pk catch-all
    #      e.g. listings/<pk>/boost/ and listings/<pk>/bookmark/ MUST precede
    #           listings/<pk>/  — otherwise Django matches the bare <pk>/ route
    #           and the trailing "boost" or "bookmark" becomes part of the pk value,
    #           causing a 404 because no listing has pk="abc123/boost".
    #   3. Bare pk catch-all last  (listings/<pk>/)
    path('listings/', ShopListingListCreateView.as_view(), name='listings'),
    path('listings/my/', MyShopListingsView.as_view(), name='my_listings'),         # literal — before <pk>
    path('listings/<str:pk>/bookmark/', BookmarkListingView.as_view(), name='bookmark_listing'),  # suffix before bare pk
    path('listings/<str:pk>/boost/', BoostListingView.as_view(), name='boost_listing'),           # suffix before bare pk
    path('listings/<str:pk>/', ShopListingDetailView.as_view(), name='listing_detail'),           # bare pk — last
    path('boosted/', BoostedListingsView.as_view(), name='boosted_listings'),

    # ── Document management ──────────────────────────────────────────────────
    path('documents/<str:pk>/', DeleteShopDocumentView.as_view(), name='delete_shop_document'),
    path('<str:shop_id>/documents/', UploadShopDocumentView.as_view(), name='upload_shop_document'),

    # ── Admin ────────────────────────────────────────────────────────────────
    path('admin/shops/pending/', AdminPendingApprovalsView.as_view(), name='admin_pending_shops'),
    path('admin/shops/approvals/', AdminAllShopApprovalsView.as_view(), name='admin_all_approvals'),
    path('admin/shops/stats/', AdminShopStatsView.as_view(), name='admin_shop_stats'),
    path('admin/shops/documents/review/', AdminReviewDocumentsView.as_view(), name='admin_review_documents'),
    path('admin/shops/<str:id>/approval-detail/', AdminShopApprovalDetailView.as_view(), name='admin_approval_detail'),
    path('admin/shops/<str:shop_id>/process-approval/', AdminProcessShopApprovalView.as_view(), name='admin_process_approval'),

    # �"?�"? Admin: shop items (all listings + delete) �"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�"?�
    path('admin/items/', AdminListingListView.as_view(), name='admin_listings_list'),
    path('admin/items/<str:pk>/', AdminListingDeleteView.as_view(), name='admin_listing_delete'),

    # ── Shop detail (must stay last — catches /<shop_id>/) ───────────────────
    path('<str:pk>/', ShopDetailView.as_view(), name='shop_detail'),
]