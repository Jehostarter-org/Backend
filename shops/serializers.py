from django.conf import settings
from rest_framework import serializers
from .models import Shop, Category, ShopListing, ListingImage, BoostRequest, ShopDocument, ShopApprovalRequest, SavedListing


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
    category      = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    category_name = serializers.ReadOnlyField(source='category.name')
    category_slug = serializers.ReadOnlyField(source='category.slug')
    currency      = serializers.ReadOnlyField(source='shop.currency')

    class Meta:
        model  = ShopListing
        fields = [
            'id', 'shop', 'shop_id', 'category', 'category_name', 'category_slug',
            'title', 'description', 'price', 'currency',
            'listing_type', 'condition', 'is_boosted',
            'is_available', 'images', 'created_at',
        ]
        read_only_fields = ['id', 'shop', 'shop_id', 'is_boosted', 'created_at']

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
    Accepts either:
      • multipart/form-data with flat business_* fields + repeated `documents` files
      • JSON with nested `approval_request` object (documents must still be uploaded separately)
    """
    APPROVAL_FIELDS = (
        'business_name', 'registration_number', 'tax_number', 'business_address',
        'business_phone', 'business_email', 'business_description',
        'years_in_business', 'employee_count',
    )

    approval_request = ShopApprovalRequestSerializer(required=False, write_only=True)

    # Flat fields for FormData clients (write-only; merged into approval_request in validate)
    business_name        = serializers.CharField(write_only=True, required=False)
    registration_number  = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    tax_number           = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    business_address     = serializers.CharField(write_only=True, required=False)
    business_phone       = serializers.CharField(write_only=True, required=False)
    business_email       = serializers.EmailField(write_only=True, required=False)
    business_description = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    years_in_business    = serializers.IntegerField(write_only=True, required=False, default=0, min_value=0)
    employee_count       = serializers.IntegerField(write_only=True, required=False, default=1, min_value=1)

    documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        help_text="Upload at least 2 documents for verification",
    )
    document_types = serializers.ListField(
        child=serializers.ChoiceField(choices=ShopDocument.DOCUMENT_TYPES),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'description', 'city', 'state_province',
            'whatsapp', 'website', 'logo', 'banner',
            'approval_request',
            'business_name', 'registration_number', 'tax_number', 'business_address',
            'business_phone', 'business_email', 'business_description',
            'years_in_business', 'employee_count',
            'documents', 'document_types',
        ]
        read_only_fields = ['id']

    def _documents_from_request(self):
        request = self.context.get('request')
        if not request:
            return []
        return request.FILES.getlist('documents')

    def validate(self, attrs):
        approval_data = attrs.pop('approval_request', None) or {}

        for field in self.APPROVAL_FIELDS:
            if field in attrs:
                approval_data[field] = attrs.pop(field)

        required = ['business_name', 'business_address', 'business_phone', 'business_email']
        missing = [f for f in required if not approval_data.get(f)]
        if missing:
            raise serializers.ValidationError({
                field: 'This field is required.' for field in missing
            })

        documents = attrs.get('documents') or self._documents_from_request()
        if len(documents) < 2:
            raise serializers.ValidationError({
                'documents': 'Please upload at least 2 documents for verification.',
            })

        attrs['approval_request'] = approval_data
        attrs['documents'] = documents
        return attrs

    def create(self, validated_data):
        approval_data = validated_data.pop('approval_request')
        documents = validated_data.pop('documents')
        document_types = validated_data.pop('document_types', None)
        user = self.context['request'].user

        shop = Shop.objects.create(
            owner=user,
            country_code=user.current_country,
            currency=settings.COUNTRY_CURRENCY_MAP.get(user.current_country, 'USD'),
            location=user.location,
            is_active=False,
            **validated_data
        )

        approval_request = ShopApprovalRequest.objects.create(
            shop=shop,
            status='draft',
            **approval_data
        )

        default_types = [choice[0] for choice in ShopDocument.DOCUMENT_TYPES]
        for index, doc_file in enumerate(documents):
            if document_types and index < len(document_types):
                doc_type = document_types[index]
            else:
                doc_type = default_types[index % len(default_types)]

            ShopDocument.objects.create(
                shop=shop,
                document_type=doc_type,
                document_file=doc_file,
                document_name=doc_file.name,
            )

        approval_request.submit_for_approval()
        return shop


class ShopApprovalStatusSerializer(serializers.ModelSerializer):
    approval_request = ShopApprovalRequestSerializer(read_only=True)
    documents_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'is_active', 'created_at',
            'approval_request', 'documents_status'
        ]
    
    def get_documents_status(self, obj):
        documents = obj.documents.all()
        return {
            'total': documents.count(),
            'pending': documents.filter(status='pending').count(),
            'approved': documents.filter(status='approved').count(),
            'rejected': documents.filter(status='rejected').count()
        }


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