from django.urls import path
from .views import (
    CategoryListView, ShopCreateView, ShopDetailView, MyShopView,
    ShopListingListCreateView, ShopListingDetailView,
    BoostListingView, BoostedListingsView,
)

urlpatterns = [
    path('categories/', CategoryListView.as_view(), name='categories'),
    path('create/', ShopCreateView.as_view(), name='shop_create'),
    path('my/', MyShopView.as_view(), name='my_shop'),
    path('<str:pk>/', ShopDetailView.as_view(), name='shop_detail'),
    path('listings/', ShopListingListCreateView.as_view(), name='listings'),
    path('listings/<str:pk>/', ShopListingDetailView.as_view(), name='listing_detail'),
    path('listings/<str:pk>/boost/', BoostListingView.as_view(), name='boost_listing'),
    path('boosted/', BoostedListingsView.as_view(), name='boosted_listings'),
] 
