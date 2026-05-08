"""
schema/queries.py
"""

import math
import strawberry
from strawberry.types import Info
from typing import Optional
from django.db.models import Q

from .types import (
    UserType, NotificationType, CommunityType, PostType,
    ShopListingType, ServiceRequestType, MigrationSpecialistType,
    MembershipPlanType, UserMembershipType,
)
from notifications.models import Notification
from community.models import Community, Post
from shops.models import ShopListing
from services.models import ServiceRequest, MigrationSpecialist
from memberships.models import MembershipPlan, UserMembership


def haversine_distance_km(lat1, lon1, lat2, lon2) -> float:
    # Calculate straight-line distance between two GPS coordinates
    R = 6371
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@strawberry.type
class Query:

    # ── Current User ──────────────────────────────────────────────────────────

    @strawberry.field
    def me(self, info: Info) -> Optional[UserType]:
        user = info.context.request.user
        if user.is_anonymous:
            return None
        return user

    # ── Notifications ─────────────────────────────────────────────────────────

    @strawberry.field
    def my_notifications(
        self,
        info: Info,
        unread_only: bool = False,
        limit: int = 20,
    ) -> list[NotificationType]:
        user = info.context.request.user
        qs = Notification.objects.filter(recipient=user)
        if unread_only:
            qs = qs.filter(is_read=False)
        return list(qs[:limit])

    @strawberry.field
    def unread_notification_count(self, info: Info) -> int:
        user = info.context.request.user
        return Notification.objects.filter(recipient=user, is_read=False).count()

    # ── Communities ───────────────────────────────────────────────────────────

    @strawberry.field
    def communities(
        self,
        info: Info,
        country_code: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
    ) -> list[CommunityType]:
        qs = Community.objects.filter(is_active=True, visibility='public')
        if country_code:
            qs = qs.filter(country_code=country_code)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return list(qs[:limit])

    @strawberry.field
    def community(self, info: Info, slug: str) -> Optional[CommunityType]:
        try:
            return Community.objects.get(slug=slug, is_active=True)
        except Community.DoesNotExist:
            return None

    @strawberry.field
    def community_posts(
        self,
        info: Info,
        community_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[PostType]:
        return list(
            Post.objects.filter(
                community_id=community_id,
                is_deleted=False,
                is_approved=True,
            ).select_related('author', 'community')[offset:offset + limit]
        )

    # ── Shop Listings ─────────────────────────────────────────────────────────

    @strawberry.field
    def listings(
        self,
        info: Info,
        # GPS coordinates from the user's device (sent by frontend)
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
        radius_km: float = 20,
        # Gold members can pass any country code to browse globally
        country_code: Optional[str] = None,
        # Standard filters
        category_id: Optional[str] = None,
        listing_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ShopListingType]:
        user = info.context.request.user
        plan = user.membership_plan  # 'free', 'silver', or 'gold'

        qs = ShopListing.objects.filter(
            is_available=True,
            is_deleted=False,
        ).select_related('shop', 'category')

        # ── Membership-based country visibility ───────────────────────────────
        if plan == 'gold':
            # Gold members can browse any country.
            # If they pass a country_code, filter by it.
            # Otherwise default to their current country.
            if country_code:
                qs = qs.filter(shop__country_code=country_code)
            else:
                qs = qs.filter(shop__country_code=user.current_country)
        else:
            # Free and Silver members are limited to:
            # 1. Their current country (where they are now)
            # 2. Their destination country (so they can browse before they arrive)
            allowed = [user.current_country]
            if user.destination_country and user.destination_country != user.current_country:
                allowed.append(user.destination_country)
            qs = qs.filter(shop__country_code__in=allowed)

        # ── Proximity filter ──────────────────────────────────────────────────
        # Only apply proximity when the user sends their GPS coordinates
        # AND they are browsing their own current country (not destination/gold)
        browsing_current_country = (
            not country_code or country_code == user.current_country
        )
        if user_lat and user_lng and browsing_current_country:
            # Split into shops that have coordinates and those that don't
            qs_with_coords = qs.exclude(
                shop__latitude=None
            ).exclude(
                shop__longitude=None
            )
            qs_no_coords = qs.filter(
                Q(shop__latitude=None) | Q(shop__longitude=None)
            )

            # Run haversine on shops that have coordinates
            nearby_ids = [
                listing.id
                for listing in qs_with_coords
                if haversine_distance_km(
                    user_lat, user_lng,
                    listing.shop.latitude, listing.shop.longitude,
                ) <= radius_km
            ]

            # Keep nearby shops + shops without coordinates
            # (shops without coords fall back to country-level visibility)
            qs = ShopListing.objects.filter(
                Q(id__in=nearby_ids) | Q(id__in=qs_no_coords.values_list('id', flat=True))
            ).select_related('shop', 'category')

        # ── Standard filters ──────────────────────────────────────────────────
        if category_id:
            qs = qs.filter(category_id=category_id)
        if listing_type:
            qs = qs.filter(listing_type=listing_type)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        # Boosted listings always come first (set in ShopListing.Meta.ordering)
        return list(qs[offset:offset + limit])

    # ── Services ──────────────────────────────────────────────────────────────

    @strawberry.field
    def my_service_requests(self, info: Info) -> list[ServiceRequestType]:
        user = info.context.request.user
        return list(
            ServiceRequest.objects.filter(requester=user).select_related('provider')
        )

    @strawberry.field
    def my_service_provisions(self, info: Info) -> list[ServiceRequestType]:
        user = info.context.request.user
        return list(
            ServiceRequest.objects.filter(provider=user).select_related('requester')
        )

    @strawberry.field
    def migration_specialists(
        self,
        info: Info,
        country_code: Optional[str] = None,
    ) -> list[MigrationSpecialistType]:
        qs = MigrationSpecialist.objects.filter(is_verified=True, is_available=True)
        if country_code:
            qs = qs.filter(countries_served__contains=[country_code])
        return list(qs.select_related('user'))

    # ── Memberships ───────────────────────────────────────────────────────────

    @strawberry.field
    def membership_plans(
        self,
        info: Info,
        country_code: str,
    ) -> list[MembershipPlanType]:
        return list(MembershipPlan.objects.filter(country_code=country_code))

    @strawberry.field
    def my_membership(self, info: Info) -> Optional[UserMembershipType]:
        user = info.context.request.user
        return UserMembership.objects.filter(user=user, is_active=True).first()