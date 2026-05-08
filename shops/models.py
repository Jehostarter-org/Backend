import ulid
from django.db import models
from django.conf import settings


def generate_ulid():
    return str(ulid.new())


class Category(models.Model):
    """Product/listing categories e.g. Electronics, Furniture, Cars."""
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
    Currency is auto-set from country_code on save and cannot be changed manually.
    Location coordinates enable proximity-based filtering (Haversine).
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    owner          = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shop')
    name           = models.CharField(max_length=200)
    description    = models.TextField(blank=True)
    country_code   = models.CharField(max_length=2)
    city           = models.CharField(max_length=100, blank=True)
    state_province = models.CharField(max_length=100, blank=True)  # e.g. "Lagos State", "New South Wales"

    # ── Currency: auto-derived from country_code, never set manually ──────────
    # This ensures Nigerian shops always show NGN, Australian shops AUD, etc.
    currency = models.CharField(max_length=3, editable=False)

    # ── Coordinates for proximity filtering ───────────────────────────────────
    # Set when shop is created (from user's GPS or entered address).
    # Used for "show shops near me" filtering (Haversine distance calculation).
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

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
        # Auto-set currency from country_code on every save.
        # This means currency is always correct and never manually overrideable.
        self.currency = settings.COUNTRY_CURRENCY_MAP.get(self.country_code, 'USD')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.city}, {self.country_code})"


class ShopListing(models.Model):
    """
    An item listed in a shop — for sale, rent, or as a service.
    Boosted listings float to top of dashboard.

    Visibility rules (enforced at query level, not model level):
    - Free/Silver users  → see listings only in their current_country
    - Gold users         → see listings in any country (global browse)
    - All users          → see listings in their destination_country
      (so someone still in Nigeria planning to move to Australia sees AU shops)
    """
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

    # ── Boost ─────────────────────────────────────────────────────────────────
    is_boosted       = models.BooleanField(default=False)
    boost_expires_at = models.DateTimeField(null=True, blank=True)

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_listings'
        # Boosted items always float to top, then newest first
        ordering = ['-is_boosted', '-created_at']

    def __str__(self):
        return f"{self.title} [{self.shop.currency}]"

    @property
    def currency(self):
        """Convenience: listing currency always comes from its shop's country."""
        return self.shop.currency


class ListingImage(models.Model):
    """Multiple images per listing."""
    id         = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    listing    = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='images')
    image      = models.ImageField(upload_to='listing_images/')
    is_primary = models.BooleanField(default=False)
    order      = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'listing_images'
        ordering = ['order']


class BoostRequest(models.Model):
    """
    Tracks paid listing boosts.
    Admin approves after confirming payment — sets is_boosted=True on the listing.
    """
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
    approved_at       = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'boost_requests'

    def __str__(self):
        return f"Boost – {self.listing.title} ({'approved' if self.approved else 'pending'})"


class SavedListing(models.Model):
    """Users can save/wishlist listings."""
    id       = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    user     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_listings')
    listing  = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'saved_listings'
        unique_together = ('user', 'listing')