"""
schema/queries.py

All resolver methods are async and wrap Django ORM calls in sync_to_async
to avoid SynchronousOnlyOperation errors when running under Daphne/ASGI.
"""

import math
import strawberry
from strawberry.types import Info
from typing import Optional
from django.db.models import Q
from asgiref.sync import sync_to_async

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
    R = 6371
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi    = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@strawberry.type
class Query:

    # ── Current User ──────────────────────────────────────────────────────────

    @strawberry.field
    async def me(self, info: Info) -> Optional[UserType]:
        user = info.context.request.user
        if user.is_anonymous:
            return None
        return user

    # ── Notifications ─────────────────────────────────────────────────────────

    @strawberry.field
    async def my_notifications(
        self,
        info: Info,
        unread_only: bool = False,
        limit: int = 20,
    ) -> list[NotificationType]:
        user = info.context.request.user
        if user.is_anonymous:
            return []

        @sync_to_async
        def fetch():
            qs = Notification.objects.filter(recipient=user)
            if unread_only:
                qs = qs.filter(is_read=False)
            return list(qs.select_related('actor')[:limit])

        return await fetch()

    @strawberry.field
    async def unread_notification_count(self, info: Info) -> int:
        user = info.context.request.user
        if user.is_anonymous:
            return 0

        @sync_to_async
        def fetch():
            return Notification.objects.filter(
                recipient=user, is_read=False
            ).count()

        return await fetch()

    # ── Communities ───────────────────────────────────────────────────────────

    @strawberry.field
    async def communities(
        self,
        info: Info,
        country_code: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
    ) -> list[CommunityType]:

        @sync_to_async
        def fetch():
            qs = Community.objects.filter(is_active=True, visibility='public')
            if country_code:
                qs = qs.filter(country_code=country_code)
            if search:
                qs = qs.filter(
                    Q(name__icontains=search) | Q(description__icontains=search)
                )
            return list(qs[:limit])

        return await fetch()

    @strawberry.field
    async def community(self, info: Info, slug: str) -> Optional[CommunityType]:

        @sync_to_async
        def fetch():
            try:
                return Community.objects.get(slug=slug, is_active=True)
            except Community.DoesNotExist:
                return None

        return await fetch()

    @strawberry.field
    async def community_posts(
        self,
        info: Info,
        community_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[PostType]:

        @sync_to_async
        def fetch():
            return list(
                Post.objects.filter(
                    community_id=community_id,
                    is_deleted=False,
                    is_approved=True,
                ).select_related('author', 'community')[offset:offset + limit]
            )

        return await fetch()

    # ── Shop Listings ─────────────────────────────────────────────────────────

    @strawberry.field
    async def listings(
        self,
        info: Info,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
        radius_km: float = 20,
        country_code: Optional[str] = None,
        category_id: Optional[str] = None,
        listing_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ShopListingType]:
        user = info.context.request.user

        @sync_to_async
        def fetch():
            plan = user.membership_plan

            qs = ShopListing.objects.filter(
                is_available=True,
                is_deleted=False,
            ).select_related('shop', 'category')

            # Membership-based country visibility
            if plan == 'gold':
                if country_code:
                    qs = qs.filter(shop__country_code=country_code)
                else:
                    qs = qs.filter(shop__country_code=user.current_country)
            else:
                allowed = [user.current_country]
                if (user.destination_country
                        and user.destination_country != user.current_country):
                    allowed.append(user.destination_country)
                qs = qs.filter(shop__country_code__in=allowed)

            # Proximity filter
            browsing_current = (
                not country_code or country_code == user.current_country
            )
            if user_lat and user_lng and browsing_current:
                qs_with_coords = (
                    qs.exclude(shop__latitude=None)
                      .exclude(shop__longitude=None)
                )
                qs_no_coords = qs.filter(
                    Q(shop__latitude=None) | Q(shop__longitude=None)
                )
                nearby_ids = [
                    listing.id
                    for listing in qs_with_coords
                    if haversine_distance_km(
                        user_lat, user_lng,
                        listing.shop.latitude, listing.shop.longitude,
                    ) <= radius_km
                ]
                qs = ShopListing.objects.filter(
                    Q(id__in=nearby_ids)
                    | Q(id__in=qs_no_coords.values_list('id', flat=True))
                ).select_related('shop', 'category')

            if category_id:
                qs = qs.filter(category_id=category_id)
            if listing_type:
                qs = qs.filter(listing_type=listing_type)
            if search:
                qs = qs.filter(
                    Q(title__icontains=search) | Q(description__icontains=search)
                )

            return list(qs[offset:offset + limit])

        return await fetch()

    # ── Services ──────────────────────────────────────────────────────────────

    @strawberry.field
    async def my_service_requests(self, info: Info) -> list[ServiceRequestType]:
        user = info.context.request.user

        @sync_to_async
        def fetch():
            return list(
                ServiceRequest.objects.filter(requester=user)
                .select_related('provider')
            )

        return await fetch()

    @strawberry.field
    async def my_service_provisions(self, info: Info) -> list[ServiceRequestType]:
        user = info.context.request.user

        @sync_to_async
        def fetch():
            return list(
                ServiceRequest.objects.filter(provider=user)
                .select_related('requester')
            )

        return await fetch()

    @strawberry.field
    async def migration_specialists(
        self,
        info: Info,
        country_code: Optional[str] = None,
    ) -> list[MigrationSpecialistType]:

        @sync_to_async
        def fetch():
            qs = MigrationSpecialist.objects.filter(
                is_verified=True, is_available=True
            )
            if country_code:
                qs = qs.filter(countries_served__contains=[country_code])
            return list(qs.select_related('user'))

        return await fetch()

    # ── Memberships ───────────────────────────────────────────────────────────

    @strawberry.field
    async def membership_plans(
        self,
        info: Info,
        country_code: str,
    ) -> list[MembershipPlanType]:

        @sync_to_async
        def fetch():
            return list(MembershipPlan.objects.filter(country_code=country_code))

        return await fetch()

    @strawberry.field
    async def my_membership(self, info: Info) -> Optional[UserMembershipType]:
        user = info.context.request.user

        @sync_to_async
        def fetch():
            return UserMembership.objects.filter(
                user=user, is_active=True
            ).first()

        return await fetch()