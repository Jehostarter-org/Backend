from rest_framework import serializers
from .models import Shop, Category, ShopListing, ListingImage, BoostRequest


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ['id', 'name', 'slug', 'icon']


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ListingImage
        fields = ['id', 'image', 'is_primary', 'order']


class ShopListingSerializer(serializers.ModelSerializer):
    images       = ListingImageSerializer(many=True, read_only=True)
    category_name = serializers.ReadOnlyField(source='category.name')
    shop_name    = serializers.ReadOnlyField(source='shop.name')
    currency     = serializers.ReadOnlyField(source='shop.currency')

    class Meta:
        model  = ShopListing
        fields = [
            'id', 'shop', 'shop_name', 'category', 'category_name',
            'title', 'description', 'price', 'currency',
            'listing_type', 'condition', 'is_boosted',
            'is_available', 'images', 'created_at',
        ]
        read_only_fields = ['id', 'shop', 'is_boosted', 'created_at']


class ShopSerializer(serializers.ModelSerializer):
    listings_count  = serializers.SerializerMethodField()
    owner_username  = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model  = Shop
        fields = [
            'id', 'owner', 'owner_username', 'name', 'description',
            'country_code', 'city', 'currency', 'logo', 'banner',
            'whatsapp', 'website', 'is_active', 'listings_count', 'created_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at']

    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()


class BoostRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BoostRequest
        fields = ['id', 'listing', 'payment_reference', 'duration_days', 'created_at']
        read_only_fields = ['id', 'created_at']  
