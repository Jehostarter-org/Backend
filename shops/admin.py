# admin.py
from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.contrib.gis.db import models as gis_models
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone
from . import models


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'icon', 'listing_count']
    list_display_links = ['name']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    list_per_page = 50
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'icon')
        }),
    )
    
    def listing_count(self, obj):
        count = obj.listings.count()
        url = reverse('admin:shops_shoplisting_changelist') + f'?category__id__exact={obj.id}'
        return format_html('<a href="{}">{} listings</a>', url, count)
    listing_count.short_description = 'Total Listings'


class ListingImageInline(admin.TabularInline):
    model = models.ListingImage
    extra = 1
    fields = ['image_preview', 'image', 'is_primary', 'order']
    readonly_fields = ['image_preview']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover;" />', obj.image.url)
        return "-"
    image_preview.short_description = 'Preview'


class BoostRequestInline(admin.TabularInline):
    model = models.BoostRequest
    extra = 0
    fields = ['user', 'payment_reference', 'amount_paid', 'duration_days', 'approved', 'approved_at']
    readonly_fields = ['created_at']
    show_change_link = True


class SavedListingInline(admin.TabularInline):
    model = models.SavedListing
    extra = 0
    fields = ['user', 'saved_at']
    readonly_fields = ['saved_at']
    show_change_link = True


@admin.register(models.Shop)
class ShopAdmin(gis_admin.GISModelAdmin):
    list_display = ['name', 'owner_info', 'country_code', 'city', 'currency', 'is_active', 'listing_count', 'has_location']
    list_filter = ['is_active', 'country_code', 'currency', 'created_at']
    search_fields = ['name', 'owner__email', 'owner__username', 'city', 'country_code']
    raw_id_fields = ['owner']
    readonly_fields = ['id', 'created_at', 'updated_at', 'currency', 'latitude', 'longitude']
    list_per_page = 25
    list_editable = ['is_active']
    
    fieldsets = (
        ('Shop Information', {
            'fields': ('id', 'owner', 'name', 'description', 'is_active')
        }),
        ('Location Details', {
            'fields': ('country_code', 'city', 'state_province', 'location', 'latitude', 'longitude')
        }),
        ('Contact & Branding', {
            'fields': ('whatsapp', 'website', 'logo', 'banner')
        }),
        ('System Fields', {
            'fields': ('currency', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = []
    
    def owner_info(self, obj):
        owner = obj.owner
        return format_html(
            '<strong>{}</strong><br/>{}',
            owner.get_full_name() or owner.username,
            owner.email
        )
    owner_info.short_description = 'Owner'
    
    def listing_count(self, obj):
        count = obj.listings.count()
        url = reverse('admin:shops_shoplisting_changelist') + f'?shop__id__exact={obj.id}'
        return format_html('<a href="{}">{} listings</a>', url, count)
    listing_count.short_description = 'Listings'
    
    def has_location(self, obj):
        return obj.location is not None
    has_location.boolean = True
    has_location.short_description = 'Has Location'
    
    actions = ['activate_shops', 'deactivate_shops']
    
    def activate_shops(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} shops activated.')
    activate_shops.short_description = 'Activate selected shops'
    
    def deactivate_shops(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} shops deactivated.')
    deactivate_shops.short_description = 'Deactivate selected shops'


@admin.register(models.ShopListing)
class ShopListingAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'shop_link', 'category_link', 'price_display', 'listing_type', 
        'condition', 'is_available', 'is_boosted', 'boost_status', 'image_count'
    ]
    list_filter = [
        'listing_type', 'condition', 'is_available', 'is_boosted', 'is_deleted',
        'created_at', 'shop__country_code'
    ]
    search_fields = ['title', 'description', 'shop__name', 'id']
    raw_id_fields = ['shop', 'category']
    readonly_fields = ['id', 'created_at', 'updated_at', 'currency']
    list_per_page = 30
    list_editable = ['is_available', 'is_boosted']
    
    fieldsets = (
        ('Listing Information', {
            'fields': ('id', 'shop', 'category', 'title', 'description')
        }),
        ('Pricing & Type', {
            'fields': ('price', 'currency', 'listing_type', 'condition')
        }),
        ('Status', {
            'fields': ('is_available', 'is_boosted', 'boost_expires_at', 'is_deleted', 'deleted_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ListingImageInline, BoostRequestInline, SavedListingInline]

    def get_changeform_initial_data(self, request):
        return {'is_available': True}

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_available = True
        super().save_model(request, obj, form, change)
    
    def shop_link(self, obj):
        url = reverse('admin:shops_shop_change', args=[obj.shop.id])
        return format_html('<a href="{}">{}</a>', url, obj.shop.name)
    shop_link.short_description = 'Shop'
    
    def category_link(self, obj):
        if obj.category:
            url = reverse('admin:shops_category_change', args=[obj.category.id])
            return format_html('<a href="{}">{}</a>', url, obj.category.name)
        return '-'
    category_link.short_description = 'Category'
    
    def price_display(self, obj):
        return format_html('<strong>{}{}</strong>', obj.currency, obj.price)
    price_display.short_description = 'Price'
    
    def boost_status(self, obj):
        if obj.is_boosted and obj.boost_expires_at:
            if obj.boost_expires_at > timezone.now():
                remaining = (obj.boost_expires_at - timezone.now()).days
                return format_html('<span style="color: green;">Active ({}d left)</span>', remaining)
            else:
                return format_html('<span style="color: red;">Expired</span>')
        return '-'
    boost_status.short_description = 'Boost Status'
    
    def image_count(self, obj):
        count = obj.images.count()
        return format_html('<a href="{}?listing__id__exact={}">{} images</a>', 
                          reverse('admin:shops_listingimage_changelist'), obj.id, count)
    image_count.short_description = 'Images'
    
    actions = ['mark_as_available', 'mark_as_unavailable', 'boost_listings', 'delete_selected_listings']
    
    def mark_as_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f'{updated} listings marked as available.')
    mark_as_available.short_description = 'Mark as available'
    
    def mark_as_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f'{updated} listings marked as unavailable.')
    mark_as_unavailable.short_description = 'Mark as unavailable'
    
    def boost_listings(self, request, queryset):
        for listing in queryset:
            listing.is_boosted = True
            listing.boost_expires_at = timezone.now() + timezone.timedelta(days=30)
            listing.save()
        self.message_user(request, f'{queryset.count()} listings boosted for 30 days.')
    boost_listings.short_description = 'Boost listings for 30 days'
    
    def delete_selected_listings(self, request, queryset):
        queryset.update(is_deleted=True, deleted_at=timezone.now())
        self.message_user(request, f'{queryset.count()} listings soft-deleted.')
    delete_selected_listings.short_description = 'Soft delete selected listings'


@admin.register(models.ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ['id', 'listing_link', 'image_preview', 'is_primary', 'order']
    list_filter = ['is_primary', 'order']
    search_fields = ['listing__title', 'listing__shop__name']
    raw_id_fields = ['listing']
    list_editable = ['is_primary', 'order']
    list_per_page = 50
    
    def listing_link(self, obj):
        url = reverse('admin:shops_shoplisting_change', args=[obj.listing.id])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" height="80" style="object-fit: cover;" />', obj.image.url)
        return "-"
    image_preview.short_description = 'Preview'
    
    actions = ['set_as_primary']
    
    def set_as_primary(self, request, queryset):
        for image in queryset:
            image.is_primary = True
            image.save()
            # Ensure only one primary per listing
            image.listing.images.exclude(id=image.id).update(is_primary=False)
        self.message_user(request, f'{queryset.count()} images set as primary.')
    set_as_primary.short_description = 'Set as primary image'


@admin.register(models.BoostRequest)
class BoostRequestAdmin(admin.ModelAdmin):
    list_display = [
        'listing_link', 'user_info', 'payment_reference', 'amount_paid', 
        'duration_days', 'approved_status', 'approved_by_info', 'created_at'
    ]
    list_filter = ['approved', 'duration_days', 'created_at']
    search_fields = ['payment_reference', 'listing__title', 'user__email', 'user__username']
    raw_id_fields = ['listing', 'user', 'approved_by']
    readonly_fields = ['id', 'created_at']
    list_per_page = 30
    
    fieldsets = (
        ('Boost Request Details', {
            'fields': ('listing', 'user', 'payment_reference', 'amount_paid', 'duration_days')
        }),
        ('Approval Status', {
            'fields': ('approved', 'approved_by', 'approved_at')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def listing_link(self, obj):
        url = reverse('admin:shops_shoplisting_change', args=[obj.listing.id])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'
    
    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.user.get_full_name() or obj.user.username,
            obj.user.email
        )
    user_info.short_description = 'User'
    
    def approved_status(self, obj):
        if obj.approved:
            return format_html('<span style="color: green; font-weight: bold;">✓ Approved</span>')
        return format_html('<span style="color: orange; font-weight: bold;">⏳ Pending</span>')
    approved_status.short_description = 'Status'
    
    def approved_by_info(self, obj):
        if obj.approved_by:
            return str(obj.approved_by)
        return '-'
    approved_by_info.short_description = 'Approved By'
    
    actions = ['approve_requests', 'approve_and_boost_listing']
    
    def approve_requests(self, request, queryset):
        for boost_request in queryset:
            if not boost_request.approved:
                boost_request.approved = True
                boost_request.approved_by = request.user
                boost_request.approved_at = timezone.now()
                boost_request.save()
        self.message_user(request, f'{queryset.count()} boost requests approved.')
    approve_requests.short_description = 'Approve selected boost requests'
    
    def approve_and_boost_listing(self, request, queryset):
        for boost_request in queryset:
            if not boost_request.approved:
                boost_request.approved = True
                boost_request.approved_by = request.user
                boost_request.approved_at = timezone.now()
                boost_request.save()
                
                # Boost the listing
                listing = boost_request.listing
                listing.is_boosted = True
                listing.boost_expires_at = timezone.now() + timezone.timedelta(days=boost_request.duration_days)
                listing.save()
        self.message_user(request, f'{queryset.count()} boost requests approved and listings boosted.')
    approve_and_boost_listing.short_description = 'Approve & boost listing immediately'


@admin.register(models.SavedListing)
class SavedListingAdmin(admin.ModelAdmin):
    list_display = ['user_info', 'listing_link', 'saved_at']
    list_filter = ['saved_at']
    search_fields = ['user__email', 'user__username', 'listing__title']
    raw_id_fields = ['user', 'listing']
    readonly_fields = ['id', 'saved_at']
    list_per_page = 50
    
    def user_info(self, obj):
        return format_html(
            '{}<br/><small>{}</small>',
            obj.user.get_full_name() or obj.user.username,
            obj.user.email
        )
    user_info.short_description = 'User'
    
    def listing_link(self, obj):
        url = reverse('admin:shops_shoplisting_change', args=[obj.listing.id])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'


@admin.register(models.ShopDocument)
class ShopDocumentAdmin(admin.ModelAdmin):
    list_display = ['shop_link', 'document_type', 'document_name', 'status', 'uploaded_at', 'reviewed_at']
    list_filter = ['status', 'document_type', 'uploaded_at']
    search_fields = ['shop__name', 'document_name', 'shop__owner__email']
    raw_id_fields = ['shop', 'reviewed_by']
    readonly_fields = ['id', 'uploaded_at', 'document_preview']
    list_per_page = 30
    list_editable = ['status', 'document_type']
    
    fieldsets = (
        ('Document Information', {
            'fields': ('shop', 'document_type', 'document_name', 'document_file', 'document_preview')
        }),
        ('Verification Status', {
            'fields': ('status', 'rejection_reason', 'reviewed_by', 'reviewed_at')
        }),
        ('System Fields', {
            'fields': ('id', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )
    
    def shop_link(self, obj):
        url = reverse('admin:shops_shop_change', args=[obj.shop.id])
        return format_html('<a href="{}">{}</a>', url, obj.shop.name)
    shop_link.short_description = 'Shop'
    
    def document_type_display(self, obj):
        return obj.get_document_type_display()
    document_type_display.short_description = 'Document Type'
    
    def status_badge(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', 
                          color, obj.get_status_display())
    status_badge.short_description = 'Status'
    
    def document_preview(self, obj):
        if obj.document_file:
            file_url = obj.document_file.url
            if obj.document_file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                return format_html('<img src="{}" width="200" style="border: 1px solid #ddd; padding: 5px;" />', file_url)
            else:
                return format_html('<a href="{}" target="_blank">Download Document</a>', file_url)
        return "-"
    document_preview.short_description = 'Preview'
    
    actions = ['approve_documents', 'reject_documents']
    
    def approve_documents(self, request, queryset):
        updated = queryset.update(status='approved', reviewed_by=request.user, reviewed_at=timezone.now())
        self.message_user(request, f'{updated} documents approved.')
    approve_documents.short_description = 'Approve selected documents'
    
    def reject_documents(self, request, queryset):
        updated = queryset.update(status='rejected', reviewed_by=request.user, reviewed_at=timezone.now())
        self.message_user(request, f'{updated} documents rejected.')
    reject_documents.short_description = 'Reject selected documents'


@admin.register(models.ShopApprovalRequest)
class ShopApprovalRequestAdmin(admin.ModelAdmin):
    list_display = [
        'business_name', 'shop_link', 'status', 'registration_number',
        'years_in_business', 'submitted_at', 'reviewed_at'
    ]
    list_filter = ['status', 'submitted_at', 'years_in_business']
    search_fields = ['business_name', 'registration_number', 'tax_number', 'business_email', 'shop__name']
    raw_id_fields = ['shop', 'reviewed_by']
    readonly_fields = ['id', 'created_at', 'updated_at', 'submitted_at', 'reviewed_at']
    list_per_page = 30
    list_editable = ['status']
    
    fieldsets = (
        ('Shop Information', {
            'fields': ('shop', 'business_name', 'registration_number', 'tax_number')
        }),
        ('Contact Details', {
            'fields': ('business_address', 'business_phone', 'business_email')
        }),
        ('Business Details', {
            'fields': ('business_description', 'years_in_business', 'employee_count')
        }),
        ('Approval Workflow', {
            'fields': ('status', 'admin_notes', 'changes_requested_notes', 'reviewed_by', 'reviewed_at', 'submitted_at')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def shop_link(self, obj):
        url = reverse('admin:shops_shop_change', args=[obj.shop.id])
        return format_html('<a href="{}">{}</a>', url, obj.shop.name)
    shop_link.short_description = 'Shop'
    
    def status_badge(self, obj):
        colors = {
            'draft': 'gray',
            'pending': 'orange',
            'in_review': 'blue',
            'approved': 'green',
            'rejected': 'red',
            'changes_requested': 'purple'
        }
        color = colors.get(obj.status, 'gray')
        status_display = dict(models.ShopApprovalRequest.STATUS_CHOICES).get(obj.status, obj.status)
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, status_display)
    status_badge.short_description = 'Status'
    
    actions = ['mark_in_review', 'approve_requests', 'reject_requests', 'request_changes']
    
    def mark_in_review(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='in_review', reviewed_by=request.user)
        self.message_user(request, f'{updated} requests marked as in review.')
    mark_in_review.short_description = 'Mark as In Review'
    
    def approve_requests(self, request, queryset):
        for approval_request in queryset.filter(status__in=['pending', 'in_review']):
            approval_request.approve(request.user)
        self.message_user(request, f'{queryset.count()} shops approved and activated.')
    approve_requests.short_description = 'Approve selected shops'
    
    def reject_requests(self, request, queryset):
        for approval_request in queryset.filter(status__in=['pending', 'in_review']):
            approval_request.reject(request.user, "Rejected by admin")
        self.message_user(request, f'{queryset.count()} shops rejected.')
    reject_requests.short_description = 'Reject selected shops'
    
    def request_changes(self, request, queryset):
        for approval_request in queryset.filter(status__in=['pending', 'in_review']):
            approval_request.request_changes(request.user, "Please update the required information")
        self.message_user(request, f'Changes requested for {queryset.count()} shops.')
    request_changes.short_description = 'Request changes for selected shops'