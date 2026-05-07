from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from .models import Shop, Category, ShopListing, BoostRequest
from .serializers import ShopSerializer, CategorySerializer, ShopListingSerializer, BoostRequestSerializer


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class ShopCreateView(generics.CreateAPIView):
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user     = self.request.user
        currency = settings.COUNTRY_CURRENCY_MAP.get(user.current_country, 'USD')
        serializer.save(owner=user, country_code=user.current_country, currency=currency)


class ShopDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset         = Shop.objects.all()
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class MyShopView(generics.RetrieveAPIView):
    serializer_class = ShopSerializer

    def get_object(self):
        return self.request.user.shop


class ShopListingListCreateView(generics.ListCreateAPIView):
    serializer_class = ShopListingSerializer
    filter_backends  = [filters.SearchFilter, filters.OrderingFilter]
    search_fields    = ['title', 'description']
    ordering_fields  = ['price', 'created_at']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        qs      = ShopListing.objects.filter(is_available=True, is_deleted=False)
        country = self.request.query_params.get('country')
        if country:
            qs = qs.filter(shop__country_code=country)
        elif self.request.user.is_authenticated:
            user      = self.request.user
            countries = [c for c in [user.current_country, user.destination_country] if c]
            if countries:
                qs = qs.filter(shop__country_code__in=countries)
        return qs

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.shop)


class ShopListingDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = ShopListing.objects.all()
    serializer_class   = ShopListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class BoostListingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = ShopListing.objects.get(pk=pk, shop__owner=request.user)
        except ShopListing.DoesNotExist:
            return Response({'detail': 'Listing not found.'}, status=404)
        serializer = BoostRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        boost = serializer.save(listing=listing, user=request.user, approved=True)
        listing.is_boosted       = True
        listing.boost_expires_at = timezone.now() + timedelta(days=boost.duration_days)
        listing.save()
        return Response({'detail': 'Listing boosted successfully.'})


class BoostedListingsView(generics.ListAPIView):
    serializer_class   = ShopListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user    = self.request.user
        country = user.current_country
        return ShopListing.objects.filter(
            is_boosted=True, is_available=True,
            boost_expires_at__gt=timezone.now(),
            shop__country_code=country,
        ) 
