from ulid import ULID
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.contrib.gis.db import models as gis_models


def generate_ulid():
    return str(ULID())


class User(AbstractUser):
    """
    Custom user model for Jehostarter.
    Uses ULID as primary key instead of auto-increment integer.
    Location stored as PostGIS Point for fast spatial queries.
    """
    id = models.CharField(
        primary_key=True, max_length=26, default=generate_ulid, editable=False,
    )

    # Location (text)
    birth_country       = models.CharField(max_length=2, blank=True)
    current_country     = models.CharField(max_length=2, blank=True)
    destination_country = models.CharField(max_length=2, blank=True)
    city                = models.CharField(max_length=100, blank=True)
    state_province      = models.CharField(max_length=100, blank=True)

    # PostGIS Point — SRID 4326 = standard GPS (WGS84)
    # Set from GPS, IP geolocation, or timezone detection.
    # Enables fast ST_DWithin spatial queries (no Python math needed).
    location = gis_models.PointField(
        geography=True,   # geography=True → distances in metres, not degrees
        srid=4326,
        null=True,
        blank=True,
    )

    # How was location determined? Used for trust/display purposes.
    LOCATION_SOURCE = [
        ('gps',      'GPS'),
        ('ip',       'IP Geolocation'),
        ('timezone', 'Timezone Detection'),
        ('manual',   'Manual Entry'),
    ]
    location_source = models.CharField(
        max_length=10, choices=LOCATION_SOURCE, blank=True
    )

    # Profile
    phone       = models.CharField(max_length=20, blank=True)
    avatar      = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio         = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    # Migration status
    MIGRATION_STATUS = [
        ('planning',   'Planning to Migrate'),
        ('in_transit', 'In Transit'),
        ('arrived',    'Recently Arrived'),
        ('settled',    'Settled'),
    ]
    migration_status = models.CharField(max_length=20, choices=MIGRATION_STATUS, blank=True)

    # Terms & conditions acceptance
    accepted_terms    = models.BooleanField(default=False)
    accepted_terms_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def latitude(self):
        """Convenience accessor — returns float or None."""
        return self.location.y if self.location else None

    @property
    def longitude(self):
        """Convenience accessor — returns float or None."""
        return self.location.x if self.location else None

    @property
    def currency(self):
        return settings.COUNTRY_CURRENCY_MAP.get(self.current_country, 'USD')

    @property
    def active_membership(self):
        return self.memberships.filter(is_active=True).first()

    @property
    def membership_plan(self):
        m = self.active_membership
        return m.plan if m else 'free'

    def __str__(self):
        return self.email or self.username

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']