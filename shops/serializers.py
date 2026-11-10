from django.conf import settings
from rest_framework import serializers
from .models import (
    Shop, Category, ShopListing, ListingImage, BoostRequest,
    ShopDocument, ShopApprovalRequest, SavedListing,
    Order, InstallmentSchedule,
)


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
    logo        = serializers.SerializerMethodField()
    banner      = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()

    class Meta:
        model  = Shop
        fields = ['id', 'name', 'country_code', 'city', 'currency', 'logo', 'banner', 'is_verified']

    def get_is_verified(self, obj):
        try:
            return obj.approval_request.status == 'approved'
        except Exception:
            return False

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
    seller_id     = serializers.ReadOnlyField(source='shop.owner.id')
    category      = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    category_name = serializers.ReadOnlyField(source='category.name')
    category_slug = serializers.ReadOnlyField(source='category.slug')
    currency      = serializers.ReadOnlyField(source='shop.currency')

    class Meta:
        model  = ShopListing
        fields = [
            'id', 'shop', 'shop_id', 'seller_id', 'category', 'category_name', 'category_slug',
            'subcategory',
            'title', 'description', 'price', 'currency',
            'listing_type', 'condition', 'is_boosted',
            'is_available', 'images', 'created_at',
        ]
        read_only_fields = ['id', 'shop', 'shop_id', 'seller_id', 'is_boosted', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['is_available'] = True
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

    def update(self, instance, validated_data):
        request = self.context.get('request')
        instance = super().update(instance, validated_data)

        if request:
            # Delete images whose IDs are in delete_images[]
            delete_ids = request.data.getlist('delete_images') if hasattr(request.data, 'getlist') else []
            if delete_ids:
                instance.images.filter(id__in=delete_ids).delete()

            # Re-order remaining images so new uploads start after the last one
            existing_count = instance.images.count()

            # Add new images
            for index, image in enumerate(request.FILES.getlist('images')):
                ListingImage.objects.create(
                    listing=instance,
                    image=image,
                    is_primary=(existing_count == 0 and index == 0),
                    order=existing_count + index,
                )

            # Ensure the first image is marked as primary
            first = instance.images.order_by('order').first()
            if first and not first.is_primary:
                instance.images.filter(is_primary=True).update(is_primary=False)
                first.is_primary = True
                first.save(update_fields=['is_primary'])

        return instance


class AdminListingListItemSerializer(serializers.ModelSerializer):
    """Admin: a shop item (listing) for the portal Shop items page."""
    shop_name        = serializers.CharField(source='shop.name', read_only=True)
    owner_name       = serializers.CharField(source='shop.owner.get_full_name', read_only=True)
    owner_email      = serializers.CharField(source='shop.owner.email', read_only=True)
    category_name    = serializers.CharField(source='category.name', read_only=True, default=None)
    currency         = serializers.CharField(source='shop.currency', read_only=True)
    primary_image    = serializers.SerializerMethodField()
    image_count      = serializers.SerializerMethodField()

    class Meta:
        model  = ShopListing
        fields = [
            'id', 'title', 'price', 'currency', 'listing_type', 'condition',
            'category_name', 'subcategory', 'is_available', 'is_boosted',
            'shop_name', 'owner_name', 'owner_email', 'primary_image',
            'image_count', 'created_at',
        ]

    def get_primary_image(self, obj):
        prime = obj.images.filter(is_primary=True).first() or obj.images.first()
        if not prime:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(prime.image.url)
        return f"{settings.BACKEND_URL}{prime.image.url}"

    def get_image_count(self, obj):
        return obj.images.count()


class ShopSerializer(serializers.ModelSerializer):
    listings_count = serializers.SerializerMethodField()
    owner_username = serializers.ReadOnlyField(source='owner.username')
    logo           = serializers.SerializerMethodField()
    banner         = serializers.SerializerMethodField()
    is_verified    = serializers.SerializerMethodField()

    class Meta:
        model  = Shop
        fields = [
            'id', 'owner', 'owner_username', 'name', 'description',
            'country_code', 'city', 'currency', 'logo', 'banner',
            'whatsapp', 'website', 'is_active', 'is_verified', 'listings_count', 'created_at',
        ]

    def get_is_verified(self, obj):
        try:
            return obj.approval_request.status == 'approved'
        except Exception:
            return False

    def get_listings_count(self, obj):
        if hasattr(obj, '_listings_count_annotation'):
            return obj._listings_count_annotation
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


class SavedListingSerializer(serializers.ModelSerializer):
    listing = ShopListingSerializer(read_only=True)

    class Meta:
        model  = SavedListing
        fields = ['id', 'listing', 'saved_at']


class BoostRequestSerializer(serializers.ModelSerializer):
    payment_reference = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model  = BoostRequest
        fields = ['id', 'listing', 'payment_reference', 'duration_days', 'created_at']
        read_only_fields = ['id', 'listing', 'created_at']
# serializers.py - Add these serializers

class ShopDocumentSerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField()
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = ShopDocument
        fields = [
            'id', 'document_type', 'document_type_display', 'document_file',
            'document_name', 'status', 'status_display', 'rejection_reason',
            'uploaded_at', 'document_url'
        ]
        read_only_fields = ['id', 'status', 'rejection_reason', 'uploaded_at', 'document_url']
    
    def get_document_url(self, obj):
        request = self.context.get('request')
        if obj.document_file and request:
            return request.build_absolute_uri(obj.document_file.url)
        return None


class ShopApprovalRequestSerializer(serializers.ModelSerializer):
    documents = ShopDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = ShopApprovalRequest
        fields = [
            'id', 'business_name', 'registration_number', 'tax_number',
            'business_address', 'business_phone', 'business_email',
            'business_description', 'years_in_business', 'employee_count',
            'status', 'admin_notes', 'changes_requested_notes',
            'submitted_at', 'reviewed_at', 'created_at', 'documents'
        ]
        read_only_fields = [
            'id', 'status', 'admin_notes', 'changes_requested_notes',
            'submitted_at', 'reviewed_at', 'created_at', 'documents'
        ]


class ShopCreateWithApprovalSerializer(serializers.ModelSerializer):
    """
    Creates a shop that is immediately active — no approval workflow required.
    Accepts multipart/form-data or JSON.
    """

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'description', 'city', 'state_province',
            'whatsapp', 'website', 'logo', 'banner',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        user = self.context['request'].user
        return Shop.objects.create(
            owner=user,
            country_code=user.current_country,
            currency=settings.COUNTRY_CURRENCY_MAP.get(user.current_country, 'USD'),
            location=user.location,
            is_active=True,   # immediately active — no review needed
            **validated_data
        )


class ShopApprovalStatusSerializer(serializers.ModelSerializer):
    approval_request = ShopApprovalRequestSerializer(read_only=True)
    documents_status = serializers.SerializerMethodField()
    is_ready = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'is_active', 'is_ready', 'created_at',
            'approval_request', 'documents_status',
        ]

    def get_is_ready(self, obj):
        return obj.is_active
    
    def get_documents_status(self, obj):
        from django.db.models import Count, Q
        agg = obj.documents.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            rejected=Count('id', filter=Q(status='rejected')),
        )
        return agg


# Admin Serializers
class AdminShopApprovalListSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    approval_status = serializers.CharField(source='approval_request.status', read_only=True)
    documents_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'owner_name', 'owner_email', 'city',
            'is_active', 'approval_status', 'created_at', 'documents_count'
        ]
    
    def get_documents_count(self, obj):
        return obj.documents.count()


class AdminShopApprovalDetailSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()
    approval_request = ShopApprovalRequestSerializer()
    documents = ShopDocumentSerializer(many=True)
    
    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'description', 'city', 'state_province',
            'country_code', 'whatsapp', 'website', 'logo', 'banner',
            'owner', 'approval_request', 'documents', 'is_active', 'created_at'
        ]
    
    def get_owner(self, obj):
        return {
            'id': obj.owner.id,
            'name': obj.owner.get_full_name(),
            'email': obj.owner.email,
            'phone': getattr(obj.owner, 'phone_number', ''),
            'membership_plan': getattr(obj.owner, 'membership_plan', 'free'),
        }


class AdminApprovalActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject', 'request_changes'])
    notes = serializers.CharField(required=False, allow_blank=True)
    changes_requested = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if data['action'] == 'reject' and not data.get('notes'):
            raise serializers.ValidationError("Rejection reason is required")
        if data['action'] == 'request_changes' and not data.get('changes_requested'):
            raise serializers.ValidationError("Please specify what changes are needed")
        return data


class DocumentReviewSerializer(serializers.Serializer):
    document_id = serializers.CharField()
    status = serializers.ChoiceField(choices=['approved', 'rejected'])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if data['status'] == 'rejected' and not data.get('rejection_reason'):
            raise serializers.ValidationError("Rejection reason is required for rejected documents")
        return data


class InstallmentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstallmentSchedule
        fields = [
            'id', 'installment_number', 'amount', 'platform_fee_amount',
            'seller_amount', 'due_date', 'status', 'payment_id', 'paid_at', 'created_at',
        ]


class OrderSerializer(serializers.ModelSerializer):
    installments = InstallmentScheduleSerializer(many=True, read_only=True)
    listing_title = serializers.ReadOnlyField(source='listing.title')
    shop_name = serializers.ReadOnlyField(source='shop.name')

    class Meta:
        model = Order
        fields = [
            'id', 'buyer', 'shop', 'shop_name', 'listing', 'listing_title',
            'total_price', 'currency', 'payment_type', 'status',
            'stripe_customer_id', 'stripe_payment_method_id', 'transfer_group',
            'rejection_reason', 'installments', 'created_at', 'updated_at',
        ]
        read_only_fields = ['buyer', 'status', 'created_at', 'updated_at']

