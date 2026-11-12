import logging
import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from django.db.models import Q
from .models import (
    Shop, Category, ShopListing, BoostRequest, ShopDocument,
    ShopApprovalRequest, SavedListing, Order, InstallmentSchedule,
)
from .serializers import (
    ShopSerializer, CategorySerializer, ShopListingSerializer,
    BoostRequestSerializer, ShopCreateWithApprovalSerializer,
    ShopApprovalStatusSerializer, ShopApprovalRequestSerializer,
    AdminShopApprovalListSerializer, AdminShopApprovalDetailSerializer,
    AdminApprovalActionSerializer, DocumentReviewSerializer,
    ShopDocumentSerializer, SavedListingSerializer,
    AdminListingListItemSerializer, OrderSerializer, InstallmentScheduleSerializer,
)

# Default search radius
DEFAULT_RADIUS_KM = 50


class IsShopOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user


class IsListingOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.shop.owner == request.user


def _point_from_user(user):
    """Returns the user's PostGIS Point or None."""
    return user.location if user and user.is_authenticated and user.location else None


def _country_scope_filter(user):
    """
    Returns a Q filter to scope listings/shops to the user's country.
    Gold members can see all countries; everyone else sees only their own.
    Unauthenticated users see all.
    """
    if user and user.is_authenticated and user.membership_plan != 'gold' and user.current_country:
        return Q(shop__country_code=user.current_country)
    return Q()


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
            is_active    = True,
        )


class ShopDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = Shop.objects.all()
    serializer_class   = ShopSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsShopOwnerOrReadOnly]


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
            return Response(None, status=200)
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
        try:
            radius_km = float(request.query_params.get('radius', DEFAULT_RADIUS_KM))
        except (ValueError, TypeError):
            radius_km = DEFAULT_RADIUS_KM

        lat = request.query_params.get('lat')
        lon = request.query_params.get('lon')

        if lat and lon:
            try:
                point = Point(float(lon), float(lat), srid=4326)
            except (ValueError, TypeError):
                return Response({'error': 'Invalid coordinates'}, status=400)
        else:
            point = _point_from_user(user)

        base_qs = Shop.objects.filter(is_active=True)

        # Non-gold members can only see shops in their own country
        if user.membership_plan != 'gold' and user.current_country:
            base_qs = base_qs.filter(country_code=user.current_country)

        if point:
            qs = base_qs.filter(
                location__dwithin=(point, D(km=radius_km))
            ).annotate(
                distance=Distance('location', point)
            ).order_by('distance')
        else:
            countries = [c for c in [user.current_country, user.destination_country] if c]
            qs = base_qs.filter(country_code__in=countries) if countries else base_qs

        qs = qs.select_related('owner').prefetch_related('approval_request')
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class ShopListingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/shops/listings/  — proximity-aware listing browse
    POST /api/shops/listings/  — create listing (auth required, multipart for images)
    """
    serializer_class = ShopListingSerializer
    parser_classes   = [MultiPartParser, FormParser, JSONParser]
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
        qs        = ShopListing.objects.select_related('shop', 'category').prefetch_related('images').filter(is_available=True, is_deleted=False)
        try:
            radius_km = float(request.query_params.get('radius', DEFAULT_RADIUS_KM))
        except (ValueError, TypeError):
            radius_km = DEFAULT_RADIUS_KM

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)

        subcategory = request.query_params.get('subcategory')
        if subcategory:
            qs = qs.filter(subcategory__iexact=subcategory)

        country = request.query_params.get('country')
        if country:
            return qs.filter(shop__country_code=country)

        lat = request.query_params.get('lat')
        lon = request.query_params.get('lon')
        if lat and lon:
            try:
                point    = Point(float(lon), float(lat), srid=4326)
                shop_ids = _nearby_shop_ids(point, radius_km)
                return qs.filter(shop__id__in=shop_ids)
            except (ValueError, TypeError):
                pass

        qs = qs.filter(_country_scope_filter(user))

        return qs

    def perform_create(self, serializer):
        user = self.request.user

        # Auto-create a shop behind the scenes (Facebook Marketplace style)
        if not hasattr(user, 'shop'):
            country_code = user.current_country

            # Fallback: detect country from IP if user has none set
            if not country_code:
                try:
                    from users.location_view import get_ip
                    import requests as req
                    ip = get_ip(self.request)
                    res = req.get(
                        f'http://ip-api.com/json/{ip or ""}?fields=status,countryCode',
                        timeout=5,
                    )
                    data = res.json()
                    if data.get('status') == 'success':
                        country_code = data.get('countryCode', '')
                except Exception:
                    pass

            currency = settings.COUNTRY_CURRENCY_MAP.get(country_code or '', 'USD')
            Shop.objects.create(
                owner=user,
                name=f"{user.first_name or user.username}'s Store",
                country_code=country_code or '',
                currency=currency,
                location=user.location,
                city=user.city or '',
                state_province=user.state_province or '',
                is_active=True,
            )
            user.refresh_from_db()

        else:
            # Fix existing shop with empty country_code
            shop = user.shop
            if not shop.country_code:
                country_code = user.current_country
                if not country_code:
                    try:
                        from users.location_view import get_ip
                        import requests as req
                        ip = get_ip(self.request)
                        res = req.get(
                            f'http://ip-api.com/json/{ip or ""}?fields=status,countryCode',
                            timeout=5,
                        )
                        data = res.json()
                        if data.get('status') == 'success':
                            country_code = data.get('countryCode', '')
                    except Exception:
                        pass
                if country_code:
                    shop.country_code = country_code
                    shop.save()  # save() automatically sets currency from country_code

        serializer.save(shop=user.shop, is_available=True)


class MyShopListingsView(generics.ListAPIView):
    """
    GET /api/shops/listings/my/ — listings belonging ONLY to the authenticated user's shop.
    Strictly owner-scoped: no other user's listings are ever returned.
    Used by seller inventory/dashboard screens.
    """
    serializer_class   = ShopListingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['title', 'description']
    ordering_fields    = ['price', 'created_at']
    pagination_class   = None  # Disable pagination or use default DRF pagination

    def get_queryset(self):
        user = self.request.user
        
        # CRITICAL SECURITY: Only return listings for the authenticated user's shop
        # If user has no shop, return empty queryset - NEVER return all listings
        if not hasattr(user, 'shop'):
            return ShopListing.objects.none()
        
        # Double-lock: filter by both the shop's owner FK and shop relation
        return (
            ShopListing.objects
            .filter(
                shop__owner=user,  # This ensures only current user's listings
                is_deleted=False,
            )
            .select_related('shop', 'shop__owner', 'category')
            .prefetch_related('images')
            .order_by('-created_at')
        )

    def list(self, request, *args, **kwargs):
        # Safety check: if user has no shop, return empty list
        if not hasattr(request.user, 'shop'):
            return Response([], status=status.HTTP_200_OK)
        
        # Support pagination if enabled
        queryset = self.filter_queryset(self.get_queryset())
        
        # Check if pagination is configured
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ShopListingDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = ShopListing.objects.all()
    serializer_class   = ShopListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsListingOwnerOrReadOnly]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]


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
    """
    Boosted listings — non-gold members see only their country's boosted listings,
    gold members see all.
    """
    serializer_class   = ShopListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ShopListing.objects.filter(
            is_boosted=True, is_available=True, boost_expires_at__gt=timezone.now(),
        ).select_related('shop', 'category').prefetch_related('images')

        qs = qs.filter(_country_scope_filter(user))

        return qs


class MySavedListingsView(generics.ListAPIView):
    """GET /api/shops/saved/ — buyer's bookmarked listings (cart)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = SavedListingSerializer

    def get_queryset(self):
        return (
            SavedListing.objects
            .filter(user=self.request.user)
            .select_related('listing__shop', 'listing__category')
            .prefetch_related('listing__images')
            .order_by('-saved_at')
        )


class BookmarkListingView(APIView):
    """
    POST   /api/shops/listings/<pk>/bookmark/ — save listing to buyer cart
    DELETE /api/shops/listings/<pk>/bookmark/ — remove from buyer cart
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        listing = get_object_or_404(
            ShopListing,
            pk=pk,
            is_available=True,
            is_deleted=False,
        )
        _, created = SavedListing.objects.get_or_create(
            user=request.user,
            listing=listing,
        )
        serializer = ShopListingSerializer(listing, context={'request': request})
        if not created:
            return Response(
                {'detail': 'Already in your cart.', 'saved': True, 'listing': serializer.data},
                status=status.HTTP_200_OK,
            )
        return Response(
            {'detail': 'Added to your cart.', 'saved': True, 'listing': serializer.data},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, pk):
        deleted, _ = SavedListing.objects.filter(
            user=request.user,
            listing_id=pk,
        ).delete()
        if not deleted:
            return Response({'detail': 'Not in your cart.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'Removed from your cart.', 'saved': False})


class ShopCreateWithApprovalView(generics.CreateAPIView):
    """
    Create a shop — active immediately, no approval required.
    POST /api/shops/create-with-approval/
    Accepts multipart/form-data or JSON.
    """
    serializer_class   = ShopCreateWithApprovalSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def create(self, request, *args, **kwargs):
        if hasattr(request.user, 'shop'):
            return Response(
                {'detail': 'You already have a shop.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shop = serializer.save()

        return Response(
            {
                'message': 'Shop created successfully.',
                'shop': ShopSerializer(shop, context={'request': request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MyShopApprovalStatusView(generics.RetrieveAPIView):
    """
    Get current user's shop approval status
    GET /api/shops/my/approval-status/
    """
    serializer_class   = ShopApprovalStatusSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        if not hasattr(self.request.user, 'shop'):
            return None
        return self.request.user.shop

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response(
                {'has_shop': False, 'message': 'No shop created yet'},
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(instance)
        return Response({
            'has_shop': True,
            'is_ready': instance.is_active,
            'shop': serializer.data,
        })


class UploadShopDocumentView(generics.CreateAPIView):
    """
    Upload additional documents for existing shop
    POST /api/shops/<shop_id>/documents/
    """
    serializer_class   = ShopDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        shop_id = self.kwargs.get('shop_id')
        shop    = get_object_or_404(Shop, id=shop_id, owner=self.request.user)
        serializer.save(shop=shop)


class DeleteShopDocumentView(generics.DestroyAPIView):
    """
    Delete a document (only if still pending)
    DELETE /api/shops/documents/<pk>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ShopDocument.objects.filter(shop__owner=self.request.user, status='pending')

    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResubmitShopApprovalView(generics.UpdateAPIView):
    """
    Resubmit shop for approval after changes were requested
    PUT/PATCH /api/shops/my/resubmit/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return get_object_or_404(ShopApprovalRequest, shop__owner=self.request.user)

    def update(self, request, *args, **kwargs):
        approval_request = self.get_object()

        if approval_request.status != 'changes_requested':
            return Response(
                {'error': 'Cannot resubmit. Current status: ' + approval_request.status},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ShopApprovalRequestSerializer(approval_request, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        approval_request.submit_for_approval()

        return Response({
            'message': 'Shop resubmitted for approval successfully',
            'status': approval_request.status,
        })


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN VIEWS
# ──────────────────────────────────────────────────────────────────────────────

class AdminPendingApprovalsView(generics.ListAPIView):
    """Admin: List all shops pending approval — GET /api/shops/admin/shops/pending/"""
    serializer_class   = AdminShopApprovalListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Shop.objects.filter(
            is_active=False,
            approval_request__status__in=['pending', 'in_review'],
        ).select_related('owner', 'approval_request')


class AdminAllShopApprovalsView(generics.ListAPIView):
    """Admin: List all shop approval requests — GET /api/shops/admin/shops/approvals/"""
    serializer_class   = AdminShopApprovalListSerializer
    permission_classes = [IsAdminUser]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['name', 'owner__email', 'owner__first_name', 'owner__last_name']
    ordering_fields    = ['created_at', 'name']
    ordering           = ['-created_at']

    def get_queryset(self):
        queryset       = Shop.objects.select_related('owner', 'approval_request')
        status_filter  = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(approval_request__status=status_filter)
        return queryset


class AdminShopApprovalDetailView(generics.RetrieveAPIView):
    """Admin: Detailed shop approval info — GET /api/shops/admin/shops/<id>/approval-detail/"""
    serializer_class   = AdminShopApprovalDetailSerializer
    permission_classes = [IsAdminUser]
    lookup_field       = 'id'

    def get_queryset(self):
        return Shop.objects.select_related('owner', 'approval_request').prefetch_related('documents')


class AdminProcessShopApprovalView(APIView):
    """Admin: Approve / reject / request changes — POST /api/shops/admin/shops/<shop_id>/process-approval/"""
    permission_classes = [IsAdminUser]

    def post(self, request, shop_id):
        shop             = get_object_or_404(Shop, id=shop_id)
        approval_request = get_object_or_404(ShopApprovalRequest, shop=shop)

        serializer = AdminApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action            = serializer.validated_data['action']
        notes             = serializer.validated_data.get('notes', '')
        changes_requested = serializer.validated_data.get('changes_requested', '')

        if action == 'approve':
            approval_request.approve(request.user, notes)
            return Response({'message': f'Shop "{shop.name}" approved.', 'status': 'approved'})

        elif action == 'reject':
            approval_request.reject(request.user, notes)
            return Response({'message': f'Shop "{shop.name}" rejected.', 'status': 'rejected', 'reason': notes})

        elif action == 'request_changes':
            approval_request.request_changes(request.user, changes_requested)
            return Response({
                'message': f'Changes requested for "{shop.name}".',
                'status': 'changes_requested',
                'changes_needed': changes_requested,
            })


class AdminReviewDocumentsView(APIView):
    """Admin: Review a single document — POST /api/shops/admin/shops/documents/review/"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = DocumentReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document = get_object_or_404(
            ShopDocument,
            id=serializer.validated_data['document_id'],
            status='pending',
        )

        document.status           = serializer.validated_data['status']
        document.rejection_reason = serializer.validated_data.get('rejection_reason', '')
        document.reviewed_at      = timezone.now()
        document.reviewed_by      = request.user
        document.save()

        return Response({
            'message': f'Document "{document.get_document_type_display()}" marked as {document.status}.',
            'document': {
                'id': document.id,
                'status': document.status,
                'rejection_reason': document.rejection_reason,
            },
        })


class AdminShopStatsView(APIView):
    """Admin: Approval statistics — GET /api/shops/admin/shops/stats/"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({
            'shops': {
                'total':            Shop.objects.count(),
                'active':           Shop.objects.filter(is_active=True).count(),
                'pending_approval': Shop.objects.filter(approval_request__status='pending').count(),
                'rejected':         Shop.objects.filter(approval_request__status='rejected').count(),
                'changes_requested':Shop.objects.filter(approval_request__status='changes_requested').count(),
            },
            'documents': {
                'total':        ShopDocument.objects.count(),
                'pending_review': ShopDocument.objects.filter(status='pending').count(),
            },
        })


class AdminListingListView(generics.ListAPIView):
    """Admin: List every item (listing) posted in shops.

    GET /api/shops/admin/items/?q=<search>&category=<slug>&status=<active|inactive>
    """
    serializer_class   = AdminListingListItemSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = ShopListing.objects.select_related('shop', 'shop__owner', 'category').prefetch_related('images').order_by('-created_at')

        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(title__icontains=q) | Q(shop__name__icontains=q) |
                Q(shop__owner__email__icontains=q) | Q(shop__owner__username__icontains=q)
            )

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)

        status_filter = self.request.query_params.get('status')
        if status_filter == 'active':
            qs = qs.filter(is_available=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_available=False)

        return qs


class AdminListingDeleteView(APIView):
    """Admin: Delete a shop item. DELETE /api/shops/admin/items/<id>/"""
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        listing = get_object_or_404(ShopListing, pk=pk)
        title = listing.title
        listing.delete()
        return Response({'message': f'Item "{title}" deleted.'})


# ── Scenario B: Marketplace Installments & Order Flows ───────────────────────

def _charge_installment(order, installment):
    """
    Charge one installment from the buyer's saved card (off-session), keep the 10%
    platform fee and transfer the rest to the seller's Stripe Connect account.
    Raises on any payment failure so the caller can report it; the installment is only
    marked paid when both the authorization and the capture succeeded.
    """
    from utils.payment_client import payment_client

    charge_amount = float(installment.amount)
    fee_amount = round(charge_amount * 0.10, 2)  # 10% platform commission
    seller_payout = round(charge_amount - fee_amount, 2)
    group = order.transfer_group or f"order_{order.id}"

    pay_resp = payment_client.create_payment(
        user_id=order.buyer_id,
        amount=charge_amount,
        currency=order.currency or 'USD',
        purpose='shop_installment',
        resource_type='order',
        resource_id=str(order.id),
        idempotency_key=f"order_{order.id}_inst_{installment.installment_number}",
        metadata={
            'order_id': str(order.id),
            'installment_id': str(installment.id),
            'installment_number': installment.installment_number,
        },
    )
    payment_id = pay_resp.get('id')

    # Authorize with the stored payment method, then capture straight away.
    payment_client.create_hold(
        payment_id=payment_id,
        customer_id=order.stripe_customer_id or None,
        payment_method_id=order.stripe_payment_method_id or None,
        transfer_group=group,
    )
    payment_client.capture_payment(payment_id=payment_id)

    installment.status = 'paid'
    installment.paid_at = timezone.now()
    installment.payment_id = payment_id or ''
    installment.platform_fee_amount = fee_amount
    installment.seller_amount = seller_payout
    installment.save()

    transferred = False
    shop = order.shop
    if shop.stripe_account_id:
        payment_client.transfer_funds(
            destination_account=shop.stripe_account_id,
            amount=seller_payout,
            currency=order.currency or 'USD',
            source_payment_id=payment_id,
            transfer_group=group,
            metadata={
                'order_id': str(order.id),
                'installment_id': str(installment.id),
                'shop_id': str(shop.id),
            },
        )
        transferred = True

    return {
        'installment_paid': installment.installment_number,
        'charged_amount': charge_amount,
        'platform_fee': fee_amount,
        'seller_payout': seller_payout,
        'payment_id': payment_id,
        'seller_transferred': transferred,
    }


class CreateOrderView(APIView):
    """
    POST /api/shops/orders/
    Creates a new shop order (full or installment).
    For installments, generates payment schedule and initiates a SetupIntent to save the card for off-session billing.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        listing_id = request.data.get('listing_id')
        payment_type = request.data.get('payment_type', 'installment')
        if payment_type not in ('full', 'installment'):
            return Response({'detail': "payment_type must be 'full' or 'installment'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            installments_count = int(request.data.get('installments_count', 4))
        except (TypeError, ValueError):
            installments_count = 4
        # 'weekly' -> due every 7 days, anything else (default 'monthly') -> every 30 days
        interval_days = 7 if request.data.get('interval') == 'weekly' else 30

        listing = get_object_or_404(ShopListing, pk=listing_id, is_available=True)

        if listing.shop.owner == request.user:
            return Response({'detail': 'You cannot purchase items from your own shop.'}, status=status.HTTP_400_BAD_REQUEST)

        total_price = listing.price
        currency = listing.currency or 'USD'

        order = Order.objects.create(
            buyer=request.user,
            shop=listing.shop,
            listing=listing,
            total_price=total_price,
            currency=currency,
            payment_type=payment_type,
            status='pending',
            transfer_group=f"order_{uuid.uuid4().hex[:12]}",
        )

        installments_data = []
        # A full payment is simply one installment for the whole amount, so both kinds
        # of order go through the same charge path.
        if payment_type in ('full', 'installment'):
            count = 1 if payment_type == 'full' else max(1, min(installments_count, 12))
            base_amt = round(float(total_price) / count, 2)
            for i in range(1, count + 1):
                amt = base_amt if i < count else round(float(total_price) - (base_amt * (count - 1)), 2)
                due_date = timezone.now() + timedelta(days=interval_days * (i - 1))
                fee = round(amt * 0.10, 2)  # 10% platform commission
                seller_net = round(amt - fee, 2)
                inst = InstallmentSchedule.objects.create(
                    order=order,
                    installment_number=i,
                    amount=amt,
                    platform_fee_amount=fee,
                    seller_amount=seller_net,
                    due_date=due_date,
                    status='pending',
                )
                installments_data.append(inst)

        client_secret = None
        customer_id = ''
        from utils.payment_client import payment_client
        try:
            # customer_email makes the payment service create a Stripe Customer, which the
            # saved card must belong to, otherwise it cannot be charged later off-session.
            setup_res = payment_client.create_setup_intent(
                customer_email=request.user.email,
                customer_id=getattr(request.user, 'stripe_customer_id', '') or '',
                metadata={
                    'order_id': str(order.id),
                    'buyer_id': str(request.user.id),
                    'shop_id': str(listing.shop.id),
                    'resource_type': 'order',
                }
            )
            client_secret = setup_res.get('client_secret')
            customer_id = setup_res.get('customer_id') or ''
            if customer_id:
                order.stripe_customer_id = customer_id
                order.save(update_fields=['stripe_customer_id'])
        except Exception as exc:
            logger.warning("SetupIntent creation skipped/failed: %s", exc)

        return Response({
            'order': OrderSerializer(order).data,
            'client_secret': client_secret,
            'customer_id': customer_id,
        }, status=status.HTTP_201_CREATED)


class AttachOrderPaymentMethodView(APIView):
    """
    POST /api/shops/orders/<pk>/payment-method/
    Attaches confirmed Stripe PaymentMethod and Customer to order for future installment charges.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        payment_method_id = request.data.get('payment_method_id')
        customer_id = request.data.get('customer_id') or getattr(request.user, 'stripe_customer_id', '')

        if not payment_method_id:
            return Response({'detail': 'payment_method_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        order.stripe_payment_method_id = payment_method_id
        if customer_id:
            order.stripe_customer_id = customer_id
        order.save(update_fields=['stripe_payment_method_id', 'stripe_customer_id'])

        data = {
            'order_id': order.id,
            'stripe_payment_method_id': order.stripe_payment_method_id,
            'stripe_customer_id': order.stripe_customer_id,
            'status': order.status,
            'message': 'Payment method successfully attached to order.',
        }

        # Installment orders wait for admin approval (which charges installment #1).
        # A full payment has no approval step, so charge it as soon as the card is saved.
        if order.payment_type == 'full' and order.status == 'pending':
            installment = order.installments.filter(installment_number=1).first()
            if installment and installment.status != 'paid':
                try:
                    data.update(_charge_installment(order, installment))
                    order.status = 'approved'
                    order.save(update_fields=['status'])
                    data['status'] = order.status
                    data['message'] = 'Payment successful.'
                except Exception as exc:
                    logger.error("Full payment failed for Order %s: %s", order.id, exc)
                    return Response({'detail': "Payment could not be processed. Please check your card details or try another card."}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(data, status=status.HTTP_200_OK)


class MyOrdersView(generics.ListAPIView):
    """GET /api/shops/orders/ — List orders placed by current user."""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user).prefetch_related('installments', 'listing', 'shop')


class OrderDetailView(generics.RetrieveAPIView):
    """GET /api/shops/orders/<pk>/ — Retrieve order details and installment schedule."""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all().prefetch_related('installments', 'listing', 'shop')
        return Order.objects.filter(
            Q(buyer=user) | Q(shop__owner=user)
        ).prefetch_related('installments', 'listing', 'shop')


class AdminProcessOrderApprovalView(APIView):
    """
    POST /api/shops/admin/orders/<pk>/process-approval/
    Admin approves or rejects an installment order.
    On approve: automatically charges installment #1 off-session, retains 10% platform fee,
    and transfers seller net amount to shop's Stripe Connected Account.
    On reject: releases hold / marks order rejected.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        action = request.data.get('action')
        reason = request.data.get('reason', '')

        if action not in ('approve', 'reject'):
            return Response({'detail': "Action must be 'approve' or 'reject'."}, status=status.HTTP_400_BAD_REQUEST)

        if action == 'reject':
            order.status = 'rejected'
            order.rejection_reason = reason
            order.save(update_fields=['status', 'rejection_reason'])
            return Response({
                'order_id': order.id,
                'status': order.status,
                'rejection_reason': order.rejection_reason,
                'message': 'Order rejected successfully.',
            }, status=status.HTTP_200_OK)

        # ── Approve flow: Charge installment #1 ──────────────────────────────
        first_installment = order.installments.filter(installment_number=1).first()
        if not first_installment:
            return Response({'detail': 'No installment schedule found for this order.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = _charge_installment(order, first_installment)
            order.status = 'approved'
            order.save(update_fields=['status'])
            return Response({
                'order_id': order.id,
                'status': order.status,
                **result,
                'message': 'Order approved and installment #1 processed.',
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error("Failed to charge installment #1 for Order %s: %s", order.id, exc)
            return Response({'detail': "Payment could not be processed. Please check your card details or try another card."}, status=status.HTTP_502_BAD_GATEWAY)


class AdminOrderListView(generics.ListAPIView):
    """GET /api/shops/admin/orders/?status=pending — all orders, for the admin approval screen."""
    serializer_class = OrderSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Order.objects.all().prefetch_related('installments', 'listing', 'shop')
        order_status = self.request.query_params.get('status')
        if order_status:
            qs = qs.filter(status=order_status)
        return qs


class ShopOrdersView(generics.ListAPIView):
    """GET /api/shops/orders/shop/ — orders placed on the current user's shop (seller view)."""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(shop__owner=self.request.user).prefetch_related('installments', 'listing', 'shop')


# ── Shop Seller Stripe Connect Onboarding ─────────────────────────────────────

class ShopStripeConnectOnboardingView(APIView):
    """
    POST /api/shops/stripe-connect/
    Creates a Stripe Express connected account for the current user's shop and returns an onboarding URL.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        shop = getattr(request.user, 'shop', None)
        if not shop:
            return Response({'detail': 'You do not own a shop.'}, status=status.HTTP_404_NOT_FOUND)

        from utils.payment_client import payment_client
        try:
            if not shop.stripe_account_id:
                acc_resp = payment_client.create_connected_account(
                    email=request.user.email,
                    country=shop.country_code or 'US',
                    business_type='company' if getattr(getattr(shop, 'approval_request', None), 'business_name', '') else 'individual',
                    metadata={
                        'shop_id': str(shop.id),
                        'owner_id': str(request.user.id),
                    }
                )
                shop.stripe_account_id = acc_resp.get('account_id')
                shop.save(update_fields=['stripe_account_id'])

            refresh_url = request.data.get('refresh_url') or f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/payouts?connect=refresh"
            return_url = request.data.get('return_url') or f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/payouts?connect=return"

            link_resp = payment_client.create_account_link(
                account_id=shop.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
            )

            return Response({
                'account_id': shop.stripe_account_id,
                'onboarding_url': link_resp.get('onboarding_url') or link_resp.get('url'),
                'expires_at': link_resp.get('expires_at'),
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error("Shop Stripe Connect onboarding error: %s", exc)
            return Response({'detail': "Payout setup is temporarily unavailable. Please try again later or contact support."}, status=status.HTTP_502_BAD_GATEWAY)


class ShopStripeConnectStatusView(APIView):
    """
    GET /api/shops/stripe-connect/status/
    Refreshes onboarding and payout status for the seller's Stripe Connect account.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        shop = getattr(request.user, 'shop', None)
        if not shop or not shop.stripe_account_id:
            return Response({
                'connected': False,
                'account_id': getattr(shop, 'stripe_account_id', None),
                'charges_enabled': False,
                'payouts_enabled': False,
                'onboarding_completed': False,
            }, status=status.HTTP_200_OK)

        from utils.payment_client import payment_client
        try:
            acc = payment_client.get_connected_account(shop.stripe_account_id)
            charges_enabled = acc.get('charges_enabled', False)
            payouts_enabled = acc.get('payouts_enabled', False)
            details_submitted = acc.get('details_submitted', False)

            shop.stripe_onboarding_completed = details_submitted
            shop.save(update_fields=['stripe_onboarding_completed'])

            return Response({
                'connected': True,
                'account_id': shop.stripe_account_id,
                'charges_enabled': charges_enabled,
                'payouts_enabled': payouts_enabled,
                'onboarding_completed': shop.stripe_onboarding_completed,
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error("Failed to fetch shop Stripe account %s: %s", shop.stripe_account_id, exc)
            return Response({'detail': "We could not load your payout status right now. Please try again later."}, status=status.HTTP_502_BAD_GATEWAY)