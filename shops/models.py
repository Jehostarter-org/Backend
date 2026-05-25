from ulid import ULID
from django.db import models
from django.conf import settings
from django.contrib.gis.db import models as gis_models


def generate_ulid():
    return str(ULID())


class Category(models.Model):
    id   = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'shop_categories'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Shop(models.Model):
    """
    A shop belongs to one user (Silver or Gold member).
    Location stored as PostGIS Point — enables fast ST_DWithin radius queries.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    owner          = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shop')
    name           = models.CharField(max_length=200)
    description    = models.TextField(blank=True)
    country_code   = models.CharField(max_length=2)
    city           = models.CharField(max_length=100, blank=True)
    state_province = models.CharField(max_length=100, blank=True)
    currency       = models.CharField(max_length=3, editable=False)

    # PostGIS Point — geography=True means ST_DWithin radius is in metres
    location = gis_models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
    )

    logo      = models.ImageField(upload_to='shop_logos/', null=True, blank=True)
    banner    = models.ImageField(upload_to='shop_banners/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    whatsapp  = models.CharField(max_length=20, blank=True)
    website   = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shops'

    def save(self, *args, **kwargs):
        self.currency = settings.COUNTRY_CURRENCY_MAP.get(self.country_code, 'USD')
        super().save(*args, **kwargs)

    @property
    def latitude(self):
        return self.location.y if self.location else None

    @property
    def longitude(self):
        return self.location.x if self.location else None

    def __str__(self):
        return f"{self.name} ({self.city}, {self.country_code})"


class ShopListing(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    LISTING_TYPE = [
        ('sale',    'For Sale'),
        ('rent',    'For Rent'),
        ('service', 'Service'),
    ]
    CONDITION = [
        ('new',         'New'),
        ('used',        'Used'),
        ('refurbished', 'Refurbished'),
    ]

    shop         = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='listings')
    category     = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='listings')
    title        = models.CharField(max_length=300)
    description  = models.TextField()
    price        = models.DecimalField(max_digits=12, decimal_places=2)
    listing_type = models.CharField(max_length=10, choices=LISTING_TYPE, default='sale')
    condition    = models.CharField(max_length=15, choices=CONDITION, blank=True)
    is_available = models.BooleanField(default=True)

    is_boosted       = models.BooleanField(default=False)
    boost_expires_at = models.DateTimeField(null=True, blank=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_listings'
        ordering = ['-is_boosted', '-created_at']

    def __str__(self):
        return f"{self.title} [{self.shop.currency}]"

    @property
    def currency(self):
        return self.shop.currency


class ListingImage(models.Model):
    id         = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    listing    = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='images')
    image      = models.ImageField(upload_to='listing_images/')
    is_primary = models.BooleanField(default=False)
    order      = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'listing_images'
        ordering = ['order']


class BoostRequest(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    listing           = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='boost_requests')
    user              = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payment_reference = models.CharField(max_length=200)
    amount_paid       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration_days     = models.PositiveIntegerField(default=7)
    approved          = models.BooleanField(default=False)
    approved_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_boosts'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'boost_requests'

    def __str__(self):
        return f"Boost – {self.listing.title} ({'approved' if self.approved else 'pending'})"


class SavedListing(models.Model):
    id      = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_listings')
    listing = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'saved_listings'
        unique_together = ('user', 'listing')
