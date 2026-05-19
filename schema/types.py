"""
schema/types.py — PostGIS version

avatar returns a plain URL string.
latitude/longitude are @strawberry.field resolvers that read from the PointField.
"""

import strawberry
import strawberry_django
from strawberry import auto
from typing import Optional
from datetime import datetime

from users.models import User
from notifications.models import Notification
from community.models import Community, Post, Comment, CommunityMember, CommunityEvent
from shops.models import Shop, ShopListing, Category
from services.models import ServiceRequest, MigrationSpecialist
from memberships.models import UserMembership, MembershipPlan


# ─── Users ────────────────────────────────────────────────────────────────────

@strawberry_django.type(User)
class UserType:
    id: auto
    username: auto
    email: auto
    first_name: auto
    last_name: auto
    birth_country: auto
    current_country: auto
    destination_country: auto
    city: auto
    bio: auto
    is_verified: auto
    migration_status: auto
    location_source: auto
    created_at: auto

    @strawberry.field
    def avatar(self) -> Optional[str]:
        return self.avatar.url if self.avatar else None

    @strawberry.field
    def latitude(self) -> Optional[float]:
        return self.location.y if self.location else None

    @strawberry.field
    def longitude(self) -> Optional[float]:
        return self.location.x if self.location else None


# ─── Memberships ──────────────────────────────────────────────────────────────

@strawberry_django.type(MembershipPlan)
class MembershipPlanType:
    id: auto
    plan: auto
    country_code: auto
    price: auto
    currency: auto
    duration_days: auto
    can_create_shop: auto
    can_create_community: auto
    can_join_community: auto
    can_boost_products: auto
    max_shop_listings: auto


@strawberry_django.type(UserMembership)
class UserMembershipType:
    id: auto
    user: UserType
    plan: auto
    country_code: auto
    started_at: auto
    expires_at: auto
    is_active: auto


# ─── Notifications ────────────────────────────────────────────────────────────

@strawberry_django.type(Notification)
class NotificationType:
    id: auto
    recipient: UserType
    actor: Optional[UserType]
    notification_type: auto
    title: auto
    message: auto
    is_read: auto
    read_at: Optional[datetime]
    link: auto
    created_at: auto


# ─── Community ────────────────────────────────────────────────────────────────

@strawberry_django.type(Community)
class CommunityType:
    id: auto
    name: auto
    slug: auto
    description: auto
    creator: UserType
    country_code: auto
    visibility: auto
    is_active: auto
    member_count: auto
    post_count: auto
    created_at: auto


@strawberry_django.type(Comment)
class CommentType:
    id: auto
    author: UserType
    content: auto
    is_deleted: auto
    created_at: auto


@strawberry_django.type(Post)
class PostType:
    id: auto
    community: CommunityType
    author: UserType
    post_type: auto
    content: auto
    video_url: auto
    video_title: auto
    like_count: auto
    comment_count: auto
    is_deleted: auto
    created_at: auto
    comments: list[CommentType]


@strawberry_django.type(CommunityMember)
class CommunityMemberType:
    id: auto
    user: UserType
    role: auto
    is_banned: auto
    joined_at: auto


@strawberry_django.type(CommunityEvent)
class CommunityEventType:
    id: auto
    community: CommunityType
    title: auto
    description: auto
    event_type: auto
    location: auto
    event_url: auto
    starts_at: auto
    ends_at: Optional[datetime]
    is_cancelled: auto
    created_at: auto


# ─── Shops ────────────────────────────────────────────────────────────────────

@strawberry_django.type(Category)
class CategoryType:
    id: auto
    name: auto
    slug: auto
    icon: auto


@strawberry_django.type(Shop)
class ShopType:
    id: auto
    owner: UserType
    name: auto
    description: auto
    country_code: auto
    city: auto
    currency: auto
    is_active: auto
    whatsapp: auto
    website: auto
    created_at: auto

    @strawberry.field
    def latitude(self) -> Optional[float]:
        return self.location.y if self.location else None

    @strawberry.field
    def longitude(self) -> Optional[float]:
        return self.location.x if self.location else None


@strawberry_django.type(ShopListing)
class ShopListingType:
    id: auto
    shop: ShopType
    category: Optional[CategoryType]
    title: auto
    description: auto
    price: auto
    listing_type: auto
    condition: auto
    is_available: auto
    is_boosted: auto
    boost_expires_at: Optional[datetime]
    created_at: auto


# ─── Services ─────────────────────────────────────────────────────────────────

@strawberry_django.type(ServiceRequest)
class ServiceRequestType:
    id: auto
    requester: UserType
    provider: Optional[UserType]
    service_type: auto
    description: auto
    country_code: auto
    city: auto
    scheduled_at: Optional[datetime]
    status: auto
    price: auto
    currency: auto
    notes: auto
    created_at: auto
    updated_at: auto


@strawberry_django.type(MigrationSpecialist)
class MigrationSpecialistType:
    id: auto
    user: UserType
    bio: auto
    qualifications: auto
    countries_served: auto
    languages: auto
    hourly_rate: auto
    currency: auto
    is_verified: auto
    is_available: auto
    rating: auto
    total_reviews: auto


# ─── Input Types ──────────────────────────────────────────────────────────────

@strawberry.input
class CreatePostInput:
    community_id: str
    post_type: str
    content: str
    video_url: str = ''
    video_title: str = ''


@strawberry.input
class CreateCommentInput:
    post_id: str
    content: str
    parent_id: Optional[str] = None


@strawberry.input
class UpdateServiceStatusInput:
    service_request_id: str
    status: str
    notes: str = ''


@strawberry.input
class UpdateLocationInput:
    latitude:  float
    longitude: float