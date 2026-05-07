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
    Currency is locked to the country where the shop is created.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    owner        = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shop')
    name         = models.CharField(max_length=200)
    description  = models.TextField(blank=True)
    country_code = models.CharField(max_length=2)
    city         = models.CharField(max_length=100, blank=True)
    currency     = models.CharField(max_length=3)
    logo         = models.ImageField(upload_to='shop_logos/', null=True, blank=True)
    banner       = models.ImageField(upload_to='shop_banners/', null=True, blank=True)
    is_active    = models.BooleanField(default=True)
    whatsapp     = models.CharField(max_length=20, blank=True)
    website      = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shops'

    def __str__(self):
        return self.name


class ShopListing(models.Model):
    """
    An item listed in a shop — for sale, rent, or as a service.
    Boosted listings float to top of dashboard.
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

    # Boost
    is_boosted       = models.BooleanField(default=False)
    boost_expires_at = models.DateTimeField(null=True, blank=True)

    # Soft delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_listings'
        ordering = ['-is_boosted', '-created_at']

    def __str__(self):
        return self.title


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
    """Tracks paid listing boosts."""
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    listing           = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='boost_requests')
    user              = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payment_reference = models.CharField(max_length=200)
    amount_paid       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration_days     = models.PositiveIntegerField(default=7)
    approved          = models.BooleanField(default=False)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'boost_requests'

    def __str__(self):
        return f"Boost – {self.listing.title}"


class SavedListing(models.Model):
    """Users can save/wishlist listings."""
    id       = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    user     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_listings')
    listing  = models.ForeignKey(ShopListing, on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'saved_listings'
        unique_together = ('user', 'listing')