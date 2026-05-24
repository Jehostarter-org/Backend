from rest_framework import generics, permissions, filters
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D

from .models import Shop, Category, ShopListing, BoostRequest
from .serializers import ShopSerializer, CategorySerializer, ShopListingSerializer, BoostRequestSerializer

# Default search radius
DEFAULT_RADIUS_KM = 50


def _point_from_user(user):
    """Returns the user's PostGIS Point or None."""
    return user.location if user.is_authenticated and user.location else None


def _nearby_shop_ids(user_point, radius_km=DEFAULT_RADIUS_KM):
    """
    Uses PostGIS ST_DWithin to find shop IDs within radius_km of user_point.
    geography=True on both models means distance is in metres.
    This is a single fast DB query — no Python math loops.
    """
    return Shop.objects.filter(
        is_active=True,
        location__dwithin=(user_point, D(km=radius_km)),
    ).annotate(
        distance=Distance('location', user_point)
    ).order_by('distance').values_list('id', flat=True)


class CategoryListView(generics.ListAPIView):
    queryset           = Category.objects.all()
    serializer_class   = CategorySerializer
    permission_classes = [permissions.AllowAny]


class ShopCreateView(generics.CreateAPIView):
    serializer_class   = ShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user     = self.request.user
        currency = settings.COUNTRY_CURRENCY_MAP.get(user.current_country, 'USD')
        serializer.save(
            owner        = user,
            country_code = user.current_country,
            currency     = currency,
            location     = user.location,
        )


class ShopDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = Shop.objects.all()
    serializer_class   = ShopSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class MyShopView(generics.RetrieveAPIView):
    serializer_class   = ShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        if not hasattr(self.request.user, 'shop'):
            return None
        return self.request.user.shop

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response(None, status=200)  # no shop yet — not an error
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class NearbyShopsView(generics.ListAPIView):
    """
    GET /api/shops/nearby/
    Optional params:
      ?lat=6.52&lon=3.37   — explicit coords (map browsing)
      ?radius=20           — custom radius in km (default 50)
    """
    serializer_class   = ShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        user      = request.user
        radius_km = float(request.query_params.get('radius', DEFAULT_RADIUS_KM))

        lat = request.query_params.get('lat')
        lon = request.query_params.get('lon')

        if lat and lon:
            point = Point(float(lon), float(lat), srid=4326)
        else:
            point = _point_from_user(user)

        base_qs = Shop.objects.filter(is_active=True)

        if point:
            qs = base_qs.filter(
                location__dwithin=(point, D(km=radius_km))
            ).annotate(
                distance=Distance('location', point)
            ).order_by('distance')
        else:
            countries = [c for c in [user.current_country, user.destination_country] if c]
            qs = base_qs.filter(country_code__in=countries) if countries else base_qs

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class ShopListingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/shops/listings/  — proximity-aware listing browse
    POST /api/shops/listings/  — create listing (auth required)

    Query params:
      ?category=vehicles     — filter by category slug
      ?country=NG            — explicit country override
      ?search=ford           — full-text search on title/description
      ?ordering=price        — sort by price or created_at
      ?lat=6.52&lon=3.37     — explicit coords
      ?radius=20             — search radius in km (default 50)
    """
    serializer_class = ShopListingSerializer
    filter_backends  = [filters.SearchFilter, filters.OrderingFilter]
    search_fields    = ['title', 'description']
    ordering_fields  = ['price', 'created_at']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        request   = self.request
        user      = request.user if request.user.is_authenticated else None
        qs        = ShopListing.objects.filter(is_available=True, is_deleted=False)
        radius_km = float(request.query_params.get('radius', DEFAULT_RADIUS_KM))

        # ── Category filter ───────────────────────────────────────────────────
        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)

        # ── Explicit country override ─────────────────────────────────────────
        country = request.query_params.get('country')
        if country:
            return qs.filter(shop__country_code=country)

        # ── Explicit coords override ──────────────────────────────────────────
        lat = request.query_params.get('lat')
        lon = request.query_params.get('lon')
        if lat and lon:
            point    = Point(float(lon), float(lat), srid=4326)
            shop_ids = _nearby_shop_ids(point, radius_km)
            return qs.filter(shop__id__in=shop_ids)

        # ── Stored user location ──────────────────────────────────────────────
        if user:
            point = _point_from_user(user)
            if point:
                shop_ids = _nearby_shop_ids(point, radius_km)
                return qs.filter(shop__id__in=shop_ids)

            # Fallback: country filter
            countries = [c for c in [user.current_country, user.destination_country] if c]
            if countries:
                return qs.filter(shop__country_code__in=countries)

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
        boost                    = serializer.save(listing=listing, user=request.user, approved=True)
        listing.is_boosted       = True
        listing.boost_expires_at = timezone.now() + timedelta(days=boost.duration_days)
        listing.save()
        return Response({'detail': 'Listing boosted successfully.'})


class BoostedListingsView(generics.ListAPIView):
    """Boosted listings scoped to user's current location."""
    serializer_class   = ShopListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs   = ShopListing.objects.filter(
            is_boosted=True,
            is_available=True,
            boost_expires_at__gt=timezone.now(),
        )
        point = _point_from_user(user)
        if point:
            shop_ids = _nearby_shop_ids(point)
            return qs.filter(shop__id__in=shop_ids)

        return qs.filter(shop__country_code=user.current_country)