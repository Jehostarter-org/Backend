# admin.py (add to your existing admin.py file)
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib.admin import SimpleListFilter
from . import models


class ServiceRequestFilter(SimpleListFilter):
    """Custom filter to show service requests by provider assignment status"""
    title = 'Provider Assignment'
    parameter_name = 'provider_assigned'
    
    def lookups(self, request, model_admin):
        return (
            ('assigned', 'Assigned to Provider'),
            ('unassigned', 'Not Assigned'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'assigned':
            return queryset.filter(provider__isnull=False)
        if self.value() == 'unassigned':
            return queryset.filter(provider__isnull=True)


@admin.register(models.ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'service_type_badge', 'requester_info', 'provider_info',
        'location_display', 'scheduled_at_display', 'price_display', 'status',
        'has_review'
    ]
    list_filter = ['service_type', 'status', 'country_code', 'created_at', ServiceRequestFilter]
    search_fields = ['id', 'requester__email', 'requester__username', 'provider__email', 'description', 'city']
    raw_id_fields = ['requester', 'provider']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 25
    list_editable = ['status']

    fieldsets = (
        ('Service Information', {
            'fields': ('id', 'service_type', 'description', 'status')
        }),
        ('Parties Involved', {
            'fields': ('requester', 'provider')
        }),
        ('Location & Scheduling', {
            'fields': ('country_code', 'city', 'scheduled_at')
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'notes')
        }),
        ('Pickup Location', {
            'fields': (
                'pickup_address', 'pickup_latitude', 'pickup_longitude',
            ),
            'classes': ('collapse',)
        }),
        ('Arrival Location', {
            'fields': (
                'arrival_address', 'arrival_latitude', 'arrival_longitude',
            ),
            'classes': ('collapse',)
        }),
        ('Distance & Pricing Details', {
            'fields': (
                'distance_km', 'estimated_duration_min',
                'distance_price_multiplier', 'original_base_price',
                'distance_calculation_method',
            ),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def service_type_badge(self, obj):
        colors = {
            'airport_pickup': 'green',
            'home_inspection': 'blue',
            'chaperone': 'orange',
            'temporary_housing': 'teal',
            'migration_specialist': 'red'
        }
        color = colors.get(obj.service_type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, obj.get_service_type_display()
        )
    service_type_badge.short_description = 'Service Type'
    
    def requester_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.requester.get_full_name() or obj.requester.username,
            obj.requester.email
        )
    requester_info.short_description = 'Requester'
    
    def provider_info(self, obj):
        if obj.provider:
            return format_html(
                '<strong>{}</strong><br/><small>{}</small>',
                obj.provider.get_full_name() or obj.provider.username,
                obj.provider.email
            )
        return mark_safe('<span style="color: gray;">Not assigned</span>')
    provider_info.short_description = 'Provider'
    
    def location_display(self, obj):
        location_parts = []
        if obj.city:
            location_parts.append(obj.city)
        if obj.country_code:
            location_parts.append(obj.country_code)
        return ', '.join(location_parts) if location_parts else '-'
    location_display.short_description = 'Location'
    
    def scheduled_at_display(self, obj):
        if obj.scheduled_at:
            if obj.scheduled_at > timezone.now():
                return format_html('<span style="color: green;">📅 {}</span>', obj.scheduled_at.strftime('%Y-%m-%d %H:%M'))
            else:
                return format_html('<span style="color: orange;">📅 {}</span>', obj.scheduled_at.strftime('%Y-%m-%d %H:%M'))
        return '-'
    scheduled_at_display.short_description = 'Scheduled'
    
    def price_display(self, obj):
        if obj.price:
            return format_html('<strong>{}{}</strong>', obj.currency or '$', obj.price)
        return '-'
    price_display.short_description = 'Price'
    
    def status_badge(self, obj):
        colors = {
            'pending': 'orange',
            'accepted': 'blue',
            'in_progress': 'purple',
            'completed': 'green',
            'cancelled': 'red'
        }
        color = colors.get(obj.status, 'gray')
        status_display = dict(models.ServiceRequest.STATUS).get(obj.status, obj.status)
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, status_display)
    status_badge.short_description = 'Status'
    
    def has_review(self, obj):
        return hasattr(obj, 'review')
    has_review.boolean = True
    has_review.short_description = 'Reviewed'
    
    actions = ['assign_provider', 'mark_accepted', 'mark_in_progress', 'mark_completed', 'cancel_requests']
    
    def assign_provider(self, request, queryset):
        """Bulk assign provider - will need to be implemented with proper logic"""
        self.message_user(request, 'Please use the individual change form to assign providers.', level='WARNING')
    assign_provider.short_description = 'Assign provider (manual)'
    
    def mark_accepted(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='accepted')
        self.message_user(request, f'{updated} requests marked as accepted.')
    mark_accepted.short_description = 'Mark as Accepted'
    
    def mark_in_progress(self, request, queryset):
        updated = queryset.filter(status='accepted').update(status='in_progress')
        self.message_user(request, f'{updated} requests marked as in progress.')
    mark_in_progress.short_description = 'Mark as In Progress'
    
    def mark_completed(self, request, queryset):
        updated = queryset.filter(status__in=['accepted', 'in_progress']).update(
            status='completed', 
            updated_at=timezone.now()
        )
        self.message_user(request, f'{updated} requests marked as completed.')
    mark_completed.short_description = 'Mark as Completed'
    
    def cancel_requests(self, request, queryset):
        updated = queryset.exclude(status='completed').update(status='cancelled')
        self.message_user(request, f'{updated} requests cancelled.')
    cancel_requests.short_description = 'Cancel selected requests'


@admin.register(models.AirportPickup)
class AirportPickupAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'service_request_link', 'flight_number', 'airport', 
        'arrival_datetime', 'num_passengers', 'driver_info', 'status_badge'
    ]
    list_filter = ['arrival_datetime', 'airport']
    search_fields = ['flight_number', 'airport', 'service_request__requester__email']
    raw_id_fields = ['service_request', 'driver']
    readonly_fields = ['id']
    
    fieldsets = (
        ('Service Request', {
            'fields': ('service_request',)
        }),
        ('Flight Details', {
            'fields': (
                'flight_number', 'arrival_datetime', 'airport', 'terminal',
                'pickup_point',
            )
        }),
        ('Passenger Details', {
            'fields': ('num_passengers', 'num_bags', 'special_requests')
        }),
        ('Assignment', {
            'fields': ('driver',)
        }),
        ('Airport Distance', {
            'fields': (
                'distance_to_terminal_km', 'waiting_time_min',
                'suggested_pickup_spot',
            ),
            'classes': ('collapse',)
        }),
        ('Flight Tracking', {
            'fields': (
                'flight_status', 'actual_landing_time',
                'driver_arrived_at', 'passenger_picked_up_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def service_request_link(self, obj):
        url = reverse('admin:services_servicerequest_change', args=[obj.service_request.id])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.get_service_type_display())
    service_request_link.short_description = 'Service'
    
    def driver_info(self, obj):
        if obj.driver:
            return format_html(
                '{}<br/><small>{}</small>',
                obj.driver.get_full_name() or obj.driver.username,
                obj.driver.email
            )
        return mark_safe('<span style="color: gray;">Not assigned</span>')
    driver_info.short_description = 'Driver'
    
    def status_badge(self, obj):
        status = obj.service_request.status
        colors = {
            'pending': 'orange',
            'accepted': 'blue',
            'in_progress': 'purple',
            'completed': 'green',
            'cancelled': 'red'
        }
        color = colors.get(status, 'gray')
        return format_html('<span style="color: {};">{}</span>', color, status.title())
    status_badge.short_description = 'Status'
    
    actions = ['assign_driver']
    
    def assign_driver(self, request, queryset):
        self.message_user(request, 'Please edit each pickup to assign a driver.', level='WARNING')
    assign_driver.short_description = 'Assign driver (manual)'


@admin.register(models.HomeInspection)
class HomeInspectionAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'service_request_link', 'property_address_short', 
        'property_type', 'inspection_date', 'inspector_info', 'has_report'
    ]
    list_filter = ['inspection_date', 'property_type']
    search_fields = ['property_address', 'service_request__requester__email']
    raw_id_fields = ['service_request', 'inspector']
    readonly_fields = ['id']
    
    fieldsets = (
        ('Service Request', {
            'fields': ('service_request',)
        }),
        ('Property Details', {
            'fields': ('property_address', 'property_type', 'inspection_date')
        }),
        ('Inspection Details', {
            'fields': ('checklist_items',)
        }),
        ('Assignment & Results', {
            'fields': ('inspector', 'report', 'report_notes')
        }),
        ('Distance & Duration', {
            'fields': ('distance_from_inspector_km', 'inspection_duration_min'),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def service_request_link(self, obj):
        url = reverse('admin:services_servicerequest_change', args=[obj.service_request.id])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.get_service_type_display())
    service_request_link.short_description = 'Service'
    
    def property_address_short(self, obj):
        return obj.property_address[:50] + '...' if len(obj.property_address) > 50 else obj.property_address
    property_address_short.short_description = 'Address'
    
    def inspector_info(self, obj):
        if obj.inspector:
            return obj.inspector.get_full_name() or obj.inspector.username
        return '-'
    inspector_info.short_description = 'Inspector'
    
    def has_report(self, obj):
        return bool(obj.report)
    has_report.boolean = True
    has_report.short_description = 'Report Uploaded'
    
    actions = ['assign_inspector']
    
    def assign_inspector(self, request, queryset):
        self.message_user(request, 'Please edit each inspection to assign an inspector.', level='WARNING')
    assign_inspector.short_description = 'Assign inspector (manual)'


@admin.register(models.ChaperoneService)
class ChaperoneServiceAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'service_request_link', 'help_type_badge', 
        'location', 'chaperone_info', 'status_badge'
    ]
    list_filter = ['help_type']
    search_fields = ['location', 'service_request__requester__email']
    raw_id_fields = ['service_request', 'chaperone']
    readonly_fields = ['id']
    
    fieldsets = (
        ('Service Request', {
            'fields': ('service_request',)
        }),
        ('Service Details', {
            'fields': ('help_type', 'location')
        }),
        ('Assignment', {
            'fields': ('chaperone',)
        }),
        ('Distance & Duration', {
            'fields': ('distance_to_location_km', 'estimated_service_time_min'),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def service_request_link(self, obj):
        url = reverse('admin:services_servicerequest_change', args=[obj.service_request.id])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.get_service_type_display())
    service_request_link.short_description = 'Service'
    
    def help_type_badge(self, obj):
        help_display = dict(models.ChaperoneService.HELP_TYPES).get(obj.help_type, obj.help_type)
        return format_html('<span style="background-color: #3498db; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>', help_display)
    help_type_badge.short_description = 'Help Type'
    
    def chaperone_info(self, obj):
        if obj.chaperone:
            return obj.chaperone.get_full_name() or obj.chaperone.username
        return '-'
    chaperone_info.short_description = 'Chaperone'
    
    def status_badge(self, obj):
        status = obj.service_request.status
        colors = {
            'pending': 'orange',
            'accepted': 'blue',
            'in_progress': 'purple',
            'completed': 'green',
            'cancelled': 'red'
        }
        color = colors.get(status, 'gray')
        return format_html('<span style="color: {};">{}</span>', color, status.title())
    status_badge.short_description = 'Status'


@admin.register(models.TemporaryHousing)
class TemporaryHousingAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'service_request_link', 'property_address_short',
        'check_in_date', 'check_out_date', 'num_guests', 'host_info', 'status_badge'
    ]
    list_filter = ['check_in_date', 'check_out_date']
    search_fields = ['property_address', 'service_request__requester__email']
    raw_id_fields = ['service_request', 'host']
    readonly_fields = ['id']

    fieldsets = (
        ('Service Request', {
            'fields': ('service_request',)
        }),
        ('Property Details', {
            'fields': ('property_address', 'check_in_date', 'check_out_date')
        }),
        ('Guest Details', {
            'fields': ('num_guests', 'num_rooms', 'special_requests')
        }),
        ('Host', {
            'fields': ('host',)
        }),
    )

    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'

    def service_request_link(self, obj):
        url = reverse('admin:services_servicerequest_change', args=[obj.service_request.id])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.get_service_type_display())
    service_request_link.short_description = 'Service'

    def property_address_short(self, obj):
        return obj.property_address[:50] + '...' if len(obj.property_address) > 50 else obj.property_address
    property_address_short.short_description = 'Address'

    def host_info(self, obj):
        if obj.host:
            return obj.host.get_full_name() or obj.host.username
        return '-'
    host_info.short_description = 'Host'

    def status_badge(self, obj):
        status = obj.service_request.status
        colors = {
            'pending': 'orange',
            'accepted': 'blue',
            'in_progress': 'purple',
            'completed': 'green',
            'cancelled': 'red'
        }
        color = colors.get(status, 'gray')
        return format_html('<span style="color: {};">{}</span>', color, status.title())
    status_badge.short_description = 'Status'


@admin.register(models.ServiceProviderProfile)
class ServiceProviderProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user_info', 'service_type_badge', 'location_display', 
        'bio_short', 'is_active', 'registered_at'
    ]
    list_filter = ['service_type', 'country_code', 'is_active', 'registered_at']
    search_fields = ['user__email', 'user__username', 'city', 'bio']
    raw_id_fields = ['user']
    readonly_fields = ['id', 'registered_at']
    list_per_page = 30
    list_editable = ['is_active']
    
    fieldsets = (
        ('Provider Information', {
            'fields': ('user', 'service_type', 'bio', 'is_active', 'registered_at')
        }),
        ('Personal Details', {
            'fields': (
                'first_name', 'last_name', 'national_identity_number',
                'emergency_contact',
            ),
            'classes': ('collapse',)
        }),
        ('Chaperone Details', {
            'fields': (
                'sim_card_reference', 'tax_file_number_reference',
                'offers_translation_service',
            ),
            'classes': ('collapse',),
            'description': 'These fields are specific to Chaperone service providers.',
        }),
        ('Service Location', {
            'fields': ('country_code', 'city')
        }),
        ('Driver License', {
            'fields': (
                'license_number', 'license_state_country',
                'license_expiration_date', 'driver_license_image',
            ),
            'classes': ('collapse',)
        }),
        ('Vehicle Information', {
            'fields': (
                'vehicle_model', 'vehicle_year', 'vehicle_colour',
                'license_plate_number', 'vin',
            ),
            'classes': ('collapse',)
        }),
        ('Vehicle Photos', {
            'fields': (
                'front_view_picture', 'back_view_picture',
                'side_view_picture', 'interior_picture',
            ),
            'classes': ('collapse',)
        }),
        ('License Plate Photos', {
            'fields': (
                'plate_number_front_view_picture',
                'plate_number_back_view_picture',
            ),
            'classes': ('collapse',)
        }),
        ('Driver Profile & Stats', {
            'fields': (
                'profile_photo', 'total_trips', 'rating', 'total_reviews',
                'is_available', 'preferred_pickup_location',
            ),
            'classes': ('collapse',)
        }),
        ('Service Radius & Home Base', {
            'fields': (
                'max_service_distance_km', 'home_base_location',
                'home_base_latitude', 'home_base_longitude',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.user.get_full_name() or obj.user.username,
            obj.user.email
        )
    user_info.short_description = 'Provider'
    
    def service_type_badge(self, obj):
        colors = {
            'airport_pickup': 'green',
            'home_inspection': 'blue',
            'chaperone': 'orange',
            'temporary_housing': 'teal'
        }
        color = colors.get(obj.service_type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, obj.get_service_type_display()
        )
    service_type_badge.short_description = 'Service Type'
    
    def location_display(self, obj):
        return f"{obj.city}, {obj.country_code}"
    location_display.short_description = 'Location'
    
    def bio_short(self, obj):
        return obj.bio[:60] + '...' if len(obj.bio) > 60 else obj.bio
    bio_short.short_description = 'Bio'
    
    actions = ['activate_providers', 'deactivate_providers']
    
    def activate_providers(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} provider profiles activated.')
    activate_providers.short_description = 'Activate selected providers'
    
    def deactivate_providers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} provider profiles deactivated.')
    deactivate_providers.short_description = 'Deactivate selected providers'


@admin.register(models.MigrationSpecialist)
class MigrationSpecialistAdmin(admin.ModelAdmin):
    list_display = [
        'user_info', 'countries_served_display', 'languages_display', 
        'hourly_rate_display', 'is_verified', 'is_available', 'rating_display'
    ]
    list_filter = ['is_verified', 'is_available', 'currency', 'created_at']
    search_fields = ['user__email', 'user__username', 'bio', 'qualifications']
    raw_id_fields = ['user']
    readonly_fields = ['id', 'created_at', 'rating', 'total_reviews']
    list_per_page = 25
    list_editable = ['is_verified', 'is_available']
    
    fieldsets = (
        ('Specialist Information', {
            'fields': ('user', 'bio', 'qualifications')
        }),
        ('Service Details', {
            'fields': ('countries_served', 'languages', 'hourly_rate', 'currency')
        }),
        ('Verification & Status', {
            'fields': ('is_verified', 'is_available')
        }),
        ('Ratings', {
            'fields': ('rating', 'total_reviews')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.user.get_full_name() or obj.user.username,
            obj.user.email
        )
    user_info.short_description = 'Specialist'
    
    def countries_served_display(self, obj):
        if obj.countries_served:
            return ', '.join(obj.countries_served[:3]) + ('...' if len(obj.countries_served) > 3 else '')
        return '-'
    countries_served_display.short_description = 'Countries'
    
    def languages_display(self, obj):
        if obj.languages:
            return ', '.join(obj.languages)
        return '-'
    languages_display.short_description = 'Languages'
    
    def hourly_rate_display(self, obj):
        if obj.hourly_rate:
            return format_html('<strong>{}{}/hr</strong>', obj.currency or '$', obj.hourly_rate)
        return '-'
    hourly_rate_display.short_description = 'Hourly Rate'
    
    def rating_display(self, obj):
        if obj.rating > 0:
            stars = '★' * int(obj.rating) + '☆' * (5 - int(obj.rating))
            return format_html('<span style="color: #f39c12;">{}</span> ({})', stars, obj.total_reviews)
        return 'No reviews'
    rating_display.short_description = 'Rating'
    
    actions = ['verify_specialists', 'unverify_specialists', 'make_available', 'make_unavailable']
    
    def verify_specialists(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} specialists verified.')
    verify_specialists.short_description = 'Verify selected specialists'
    
    def unverify_specialists(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f'{updated} specialists unverified.')
    unverify_specialists.short_description = 'Unverify selected specialists'
    
    def make_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f'{updated} specialists marked as available.')
    make_available.short_description = 'Mark as available'
    
    def make_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f'{updated} specialists marked as unavailable.')
    make_unavailable.short_description = 'Mark as unavailable'


@admin.register(models.MigrationSpecialistApplication)
class MigrationSpecialistApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'user_info', 'countries_served_display', 'languages_display', 
        'hourly_rate_display', 'status_badge', 'submitted_at', 'reviewed_at'
    ]
    list_filter = ['status', 'submitted_at', 'currency']
    search_fields = ['user__email', 'user__username', 'bio', 'qualifications']
    raw_id_fields = ['user', 'reviewed_by']
    readonly_fields = ['id', 'submitted_at', 'reviewed_at']
    list_per_page = 25
    
    fieldsets = (
        ('Applicant Information', {
            'fields': ('user',)
        }),
        ('Professional Details', {
            'fields': ('bio', 'qualifications', 'countries_served', 'languages')
        }),
        ('Pricing', {
            'fields': ('hourly_rate', 'currency')
        }),
        ('Review & Status', {
            'fields': ('status', 'rejection_reason', 'reviewed_by', 'reviewed_at')
        }),
        ('System Fields', {
            'fields': ('id', 'submitted_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.user.get_full_name() or obj.user.username,
            obj.user.email
        )
    user_info.short_description = 'Applicant'
    
    def countries_served_display(self, obj):
        if obj.countries_served:
            return ', '.join(obj.countries_served[:3]) + ('...' if len(obj.countries_served) > 3 else '')
        return '-'
    countries_served_display.short_description = 'Countries'
    
    def languages_display(self, obj):
        if obj.languages:
            return ', '.join(obj.languages)
        return '-'
    languages_display.short_description = 'Languages'
    
    def hourly_rate_display(self, obj):
        return format_html('<strong>{}{}/hr</strong>', obj.currency, obj.hourly_rate)
    hourly_rate_display.short_description = 'Hourly Rate'
    
    def status_badge(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.status.title())
    status_badge.short_description = 'Status'
    
    actions = ['approve_applications', 'reject_applications']
    
    def approve_applications(self, request, queryset):
        approved_count = 0
        for application in queryset.filter(status='pending'):
            application.status = 'approved'
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save()
            
            # Create MigrationSpecialist profile
            models.MigrationSpecialist.objects.get_or_create(
                user=application.user,
                defaults={
                    'bio': application.bio,
                    'qualifications': application.qualifications,
                    'countries_served': application.countries_served,
                    'languages': application.languages,
                    'hourly_rate': application.hourly_rate,
                    'currency': application.currency,
                    'is_verified': True,
                    'is_available': True
                }
            )
            approved_count += 1
        
        self.message_user(request, f'{approved_count} applications approved and specialist profiles created.')
    approve_applications.short_description = 'Approve selected applications'
    
    def reject_applications(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason='Rejected by admin'
        )
        self.message_user(request, f'{updated} applications rejected.')
    reject_applications.short_description = 'Reject selected applications'


@admin.register(models.ServiceReview)
class ServiceReviewAdmin(admin.ModelAdmin):
    list_display = [
        'service_request_link', 'reviewer_info', 'rating_stars', 
        'comment_short', 'created_at'
    ]
    list_filter = ['rating', 'created_at']
    search_fields = ['service_request__id', 'reviewer__email', 'reviewer__username', 'comment']
    raw_id_fields = ['service_request', 'reviewer']
    readonly_fields = ['id', 'created_at']
    list_per_page = 30
    
    fieldsets = (
        ('Review Details', {
            'fields': ('service_request', 'reviewer', 'rating', 'comment')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def service_request_link(self, obj):
        url = reverse('admin:services_servicerequest_change', args=[obj.service_request.id])
        service_type = obj.service_request.get_service_type_display()
        return format_html('<a href="{}">{}</a>', url, service_type)
    service_request_link.short_description = 'Service'

    def reviewer_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.reviewer.get_full_name() or obj.reviewer.username,
            obj.reviewer.email
        )
    reviewer_info.short_description = 'Reviewer'

    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: #f39c12; font-size: 14px;">{}</span>', stars)
    rating_stars.short_description = 'Rating'

    def comment_short(self, obj):
        return obj.comment[:100] + '...' if len(obj.comment) > 100 else obj.comment
    comment_short.short_description = 'Comment'


@admin.register(models.DistanceCalculationLog)
class DistanceCalculationLogAdmin(admin.ModelAdmin):
    list_display = [
        'service_request_link', 'calculation_method',
        'calculated_distance_km', 'calculated_duration_min',
        'api_status_code', 'error_short', 'created_at',
    ]
    list_filter = ['calculation_method', 'api_status_code', 'created_at']
    search_fields = ['service_request__id', 'error_message']
    raw_id_fields = ['service_request']
    readonly_fields = [
        'id', 'service_request', 'calculation_method',
        'pickup_coords', 'arrival_coords',
        'calculated_distance_km', 'calculated_duration_min',
        'api_response_time_ms', 'api_status_code',
        'error_message', 'created_at',
    ]
    list_per_page = 30

    fieldsets = (
        ('Calculation Info', {
            'fields': (
                'service_request', 'calculation_method',
                'pickup_coords', 'arrival_coords',
            )
        }),
        ('Results', {
            'fields': (
                'calculated_distance_km', 'calculated_duration_min',
            )
        }),
        ('API Response', {
            'fields': (
                'api_response_time_ms', 'api_status_code',
                'error_message',
            ),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def service_request_link(self, obj):
        url = reverse('admin:services_servicerequest_change', args=[obj.service_request.id])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.id[:8])
    service_request_link.short_description = 'Service Request'

    def error_short(self, obj):
        if obj.error_message:
            return obj.error_message[:60] + '...' if len(obj.error_message) > 60 else obj.error_message
        return '—'
    error_short.short_description = 'Error'

    def has_add_permission(self, request):
        return False  # Logs are created automatically, not manually


class PropertyImageInline(admin.TabularInline):
    model = models.PropertyImage
    extra = 1
    fields = ['image_url', 'order']
    readonly_fields = []


@admin.register(models.Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = [
        'property_title', 'owner_info', 'property_type', 'rental_type',
        'city', 'country', 'price_display', 'status_badge',
        'bedrooms', 'bathrooms', 'created_at',
    ]
    list_filter = [
        'property_type', 'rental_type', 'status', 'is_published',
        'country', 'created_at',
    ]
    search_fields = [
        'property_title', 'description', 'address',
        'city', 'state', 'owner__email',
    ]
    raw_id_fields = ['owner']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 25

    fieldsets = (
        ('Basic Info', {
            'fields': (
                'owner', 'property_title', 'property_type',
                'rental_type', 'description',
            )
        }),
        ('Location', {
            'fields': ('address', 'nearest_landmark', 'city', 'state', 'country')
        }),
        ('Features', {
            'fields': ('bedrooms', 'bathrooms', 'amenities', 'images')
        }),
        ('Pricing & Availability', {
            'fields': (
                'available_from', 'price_amount', 'price_type',
                'security_deposit', 'min_stay_duration', 'max_stay_duration',
                'house_rules',
            )
        }),
        ('Status', {
            'fields': ('status', 'is_published')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PropertyImageInline]

    def owner_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.owner.get_full_name() or obj.owner.username,
            obj.owner.email
        )
    owner_info.short_description = 'Owner'

    def price_display(self, obj):
        return format_html('<strong>{}{}</strong>', obj.price_amount, obj.price_type)
    price_display.short_description = 'Price'

    def status_badge(self, obj):
        colors = {
            'draft': 'gray', 'published': 'green',
            'rented': 'blue', 'unavailable': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.status.title()
        )
    status_badge.short_description = 'Status'

    def publish_listings(self, request, queryset):
        updated = queryset.update(status='published', is_published=True)
        self.message_user(request, f'{updated} properties published.')
    publish_listings.short_description = 'Publish selected properties'

    def unpublish_listings(self, request, queryset):
        updated = queryset.update(status='draft', is_published=False)
        self.message_user(request, f'{updated} properties unpublished.')
    unpublish_listings.short_description = 'Unpublish selected properties'

    actions = ['publish_listings', 'unpublish_listings']


@admin.register(models.PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ['id', 'property_link', 'order', 'created_at']
    list_filter = ['order']
    search_fields = ['property__property_title', 'property__city']
    raw_id_fields = ['property']
    readonly_fields = ['id', 'created_at']
    list_per_page = 50

    def property_link(self, obj):
        url = reverse('admin:services_property_change', args=[obj.property.id])
        return format_html('<a href="{}">{}</a>', url, obj.property.property_title)
    property_link.short_description = 'Property'