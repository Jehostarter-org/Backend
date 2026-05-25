from rest_framework import serializers
from .models import Shop, Category, ShopListing, ListingImage, BoostRequest


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ['id', 'name', 'slug', 'icon']


class ListingImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model  = ListingImage
        fields = ['id', 'image', 'is_primary', 'order']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        if obj.image:
            from django.conf import settings
            return f"{settings.BACKEND_URL}{obj.image.url}"
        return None


class ShopBriefSerializer(serializers.ModelSerializer):
    logo   = serializers.SerializerMethodField()
    banner = serializers.SerializerMethodField()

    class Meta:
        model  = Shop
        fields = ['id', 'name', 'country_code', 'city', 'currency', 'logo', 'banner']

    def get_logo(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_banner(self, obj):
        request = self.context.get('request')
        if obj.banner and request:
            return request.build_absolute_uri(obj.banner.url)
        return None


class ShopListingSerializer(serializers.ModelSerializer):
    images        = ListingImageSerializer(many=True, read_only=True)
    shop          = ShopBriefSerializer(read_only=True)
    shop_id       = serializers.ReadOnlyField(source='shop.id')
    category      = serializers.SlugRelatedField(
                        slug_field='slug',
                        queryset=Category.objects.all(),
                    )
    category_name = serializers.ReadOnlyField(source='category.name')
    currency      = serializers.ReadOnlyField(source='shop.currency')

    class Meta:
        model  = ShopListing
        fields = [
            'id', 'shop', 'shop_id', 'category', 'category_name',
            'title', 'description', 'price', 'currency',
            'listing_type', 'condition', 'is_boosted',
            'is_available', 'images', 'created_at',
        ]
        read_only_fields = ['id', 'shop', 'shop_id', 'is_boosted', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        listing = super().create(validated_data)

        if request:
            for index, image in enumerate(request.FILES.getlist('images')):
                ListingImage.objects.create(
                    listing=listing,
                    image=image,
                    is_primary=index == 0,
                    order=index,
                )

        return listing


class ShopSerializer(serializers.ModelSerializer):
    listings_count = serializers.SerializerMethodField()
    owner_username = serializers.ReadOnlyField(source='owner.username')
    logo           = serializers.SerializerMethodField()
    banner         = serializers.SerializerMethodField()

    class Meta:
        model  = Shop
        fields = [
            'id', 'owner', 'owner_username', 'name', 'description',
            'country_code', 'city', 'currency', 'logo', 'banner',
            'whatsapp', 'website', 'is_active', 'listings_count', 'created_at',
        ]
        read_only_fields = ['id', 'owner', 'country_code', 'currency', 'created_at']

    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()

    def get_logo(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_banner(self, obj):
        request = self.context.get('request')
        if obj.banner and request:
            return request.build_absolute_uri(obj.banner.url)
        return None


class BoostRequestSerializer(serializers.ModelSerializer):
    payment_reference = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model  = BoostRequest
        fields = ['id', 'listing', 'payment_reference', 'duration_days', 'created_at']
        read_only_fields = ['id', 'listing', 'created_at']
