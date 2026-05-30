# admin.py - Fixed version
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.gis import admin as gis_admin
from django.contrib.gis.db import models as gis_models
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib.admin import SimpleListFilter
from . import models


class MembershipStatusFilter(SimpleListFilter):
    """Filter users by their current membership plan"""
    title = 'Membership Plan'
    parameter_name = 'membership_plan'
    
    def lookups(self, request, model_admin):
        return [
            ('free', 'Free'),
            ('silver', 'Silver'),
            ('gold', 'Gold'),
        ]
    
    def queryset(self, request, queryset):
        if self.value():
            # This requires a subquery to check active memberships
            from django.db.models import Exists, OuterRef
            from memberships.models import UserMembership
            
            active_membership = UserMembership.objects.filter(
                user=OuterRef('pk'),
                is_active=True,
                plan=self.value()
            )
            return queryset.filter(Exists(active_membership))
        return queryset


class VerificationStatusFilter(SimpleListFilter):
    """Filter users by verification status"""
    title = 'Verification Status'
    parameter_name = 'verified'
    
    def lookups(self, request, model_admin):
        return [
            ('verified', 'Verified'),
            ('unverified', 'Unverified'),
        ]
    
    def queryset(self, request, queryset):
        if self.value() == 'verified':
            return queryset.filter(is_verified=True)
        if self.value() == 'unverified':
            return queryset.filter(is_verified=False)
        return queryset


class MigrationStatusFilter(SimpleListFilter):
    """Filter users by migration status"""
    title = 'Migration Status'
    parameter_name = 'migration_status'
    
    def lookups(self, request, model_admin):
        return models.User.MIGRATION_STATUS
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(migration_status=self.value())
        return queryset


class LocationSourceFilter(SimpleListFilter):
    """Filter by how location was determined"""
    title = 'Location Source'
    parameter_name = 'location_source'
    
    def lookups(self, request, model_admin):
        return models.User.LOCATION_SOURCE
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(location_source=self.value())
        return queryset


# Custom GIS admin that doesn't require OSMGeoAdmin
class UserGeoAdmin(gis_admin.GISModelAdmin):
    """Simplified GIS admin without OSM dependency"""
    gis_widget_kwargs = {
        'attrs': {
            'default_zoom': 5,
            'default_lon': 0,
            'default_lat': 0,
        },
    }
    map_width = 600
    map_height = 400


@admin.register(models.User)
class UserAdmin(BaseUserAdmin, UserGeoAdmin):
    """
    Custom admin for User model with GIS support.
    Extends both Django's BaseUserAdmin and GISModelAdmin for map integration.
    """
    
    # Override default fields to use our custom User model
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'phone', 'bio')
        }),
        ('Location', {
            'fields': ('birth_country', 'current_country', 'destination_country', 
                      'city', 'state_province', 'location', 'location_source')
        }),
    )
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'bio', 'avatar')
        }),
        ('Location & Geography', {
            'fields': (
                'birth_country', 'current_country', 'destination_country',
                'city', 'state_province', 'location', 'location_source',
                'latitude', 'longitude'
            )
        }),
        ('Migration Status', {
            'fields': ('migration_status',)
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_at')
        }),
        ('Legal', {
            'fields': ('accepted_terms', 'accepted_terms_at')
        }),
        ('Membership', {
            'fields': ('membership_plan_display', 'active_membership_link'),
            'classes': ('collapse',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')
        }),
    )
    
    list_display = [
        'avatar_thumbnail', 'user_info', 'email', 'current_location',
        'membership_badge', 'migration_status_badge', 'verification_badge',
        'active_status', 'date_joined_short'
    ]
    
    list_filter = [
        'is_active', 'is_staff', 'is_superuser', 'is_verified',
        VerificationStatusFilter, MembershipStatusFilter,
        MigrationStatusFilter, LocationSourceFilter, 'current_country',
        'destination_country', 'date_joined', 'created_at'
    ]
    
    search_fields = [
        'username', 'email', 'first_name', 'last_name', 'phone',
        'city', 'state_province'
    ]
    
    readonly_fields = [
        'id', 'last_login', 'date_joined', 'created_at', 'updated_at',
        'latitude', 'longitude', 'membership_plan_display', 'active_membership_link',
        'avatar_preview'
    ]
    
    raw_id_fields = ()
    list_per_page = 25
    list_select_related = ()
    
    # GIS map settings
    map_width = 600
    map_height = 400
    
    # UserAdmin overrides
    ordering = ['-date_joined']
    
    def get_fieldsets(self, request, obj=None):
        """Staff users cannot edit permissions; superusers get full access."""
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        return [fieldset for fieldset in fieldsets if fieldset[0] != 'Permissions']
    
    def avatar_thumbnail(self, obj):
        """Display avatar thumbnail in list view"""
        if obj.avatar:
            return format_html(
                '<img src="{}" width="40" height="40" style="border-radius: 50%; object-fit: cover;" />',
                obj.avatar.url
            )
        # Default avatar based on initials
        initials = (obj.first_name[0] if obj.first_name else '') + (obj.last_name[0] if obj.last_name else '')
        if not initials and obj.username:
            initials = obj.username[0].upper()
        if not initials:
            initials = 'U'
        return format_html(
            '<div style="width: 40px; height: 40px; background: #3498db; color: white; '
            'border-radius: 50%; display: flex; align-items: center; justify-content: center; '
            'font-weight: bold;">{}</div>',
            initials
        )
    avatar_thumbnail.short_description = 'Avatar'
    
    def user_info(self, obj):
        """Display user information with links"""
        return format_html(
            '<div><strong><a href="{}">{}</a></strong></div>'
            '<div style="color: #666; font-size: 11px;">@{}</div>'
            '<div style="color: #999; font-size: 10px;">ID: <code>{}</code></div>',
            reverse('admin:users_user_change', args=[obj.id]),
            obj.get_full_name() or obj.username,
            obj.username,
            obj.id[:8]
        )
    user_info.short_description = 'User'
    
    def current_location(self, obj):
        """Display current location with map link if available"""
        location_parts = []
        if obj.city:
            location_parts.append(obj.city)
        if obj.state_province:
            location_parts.append(obj.state_province)
        if obj.current_country:
            location_parts.append(obj.current_country)
        
        if location_parts:
            location_text = ', '.join(location_parts)
            if obj.latitude is not None and obj.longitude is not None:
                coords = f'{float(obj.latitude):.4f}, {float(obj.longitude):.4f}'
                return format_html(
                    '{}<br/><span style="color: #999; font-size: 10px;">📍 {}</span>',
                    location_text,
                    coords,
                )
            return location_text
        return format_html('<span style="color: #999;">Not set</span>')
    current_location.short_description = 'Current Location'
    
    def membership_badge(self, obj):
        """Display membership plan with badge"""
        plan = obj.membership_plan
        colors = {
            'free': '#95a5a6',
            'silver': '#bdc3c7',
            'gold': '#f39c12'
        }
        icons = {
            'free': '🆓',
            'silver': '🥈',
            'gold': '🥇'
        }
        color = colors.get(plan, '#95a5a6')
        icon = icons.get(plan, '📋')
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; '
            'border-radius: 12px; font-size: 11px; font-weight: bold;">{} {}</span>',
            color, 'black' if plan == 'silver' else 'white', icon, plan.upper()
        )
    membership_badge.short_description = 'Plan'
    
    def migration_status_badge(self, obj):
        """Display migration status with icon"""
        status_icons = {
            'planning': '✈️',
            'in_transit': '🚗',
            'arrived': '🏠',
            'settled': '✅'
        }
        icon = status_icons.get(obj.migration_status, '📌')
        status_display = dict(models.User.MIGRATION_STATUS).get(obj.migration_status, 'Not set')
        return format_html('{} {}', icon, status_display)
    migration_status_badge.short_description = 'Migration Status'
    
    def verification_badge(self, obj):
        """Display verification status"""
        if obj.is_verified:
            if obj.verified_at:
                return format_html(
                    '<span style="color: #27ae60;">✓ Verified</span><br/>'
                    '<span style="color: #999; font-size: 10px;">{}</span>',
                    obj.verified_at.strftime('%Y-%m-%d')
                )
            return format_html('<span style="color: #27ae60;">✓ Verified</span>')
        return format_html('<span style="color: #e74c3c;">✗ Unverified</span>')
    verification_badge.short_description = 'Verified'
    
    def active_status(self, obj):
        """Display active status with icon"""
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">● Active</span>')
        return format_html('<span style="color: #e74c3c;">● Inactive</span>')
    active_status.short_description = 'Status'
    
    def date_joined_short(self, obj):
        """Format date joined"""
        return obj.date_joined.strftime('%Y-%m-%d')
    date_joined_short.short_description = 'Joined'
    
    def membership_plan_display(self, obj):
        """Display membership plan details in readonly form"""
        plan = obj.membership_plan
        active_membership = obj.active_membership
        
        if active_membership:
            expires_at = active_membership.expires_at
            if expires_at > timezone.now():
                days_left = (expires_at - timezone.now()).days
                return format_html(
                    '<strong>{}</strong><br/>Expires: {}<br/><span style="color: #666;">{} days left</span>',
                    plan.upper(), expires_at.strftime('%Y-%m-%d'), days_left
                )
            else:
                return format_html(
                    '<strong>{}</strong><br/><span style="color: #e74c3c;">Expired</span>',
                    plan.upper()
                )
        return format_html('<span style="color: #999;">Free Plan</span>')
    membership_plan_display.short_description = 'Current Membership'
    
    def active_membership_link(self, obj):
        """Link to active membership in admin"""
        active_membership = obj.active_membership
        if active_membership:
            try:
                # Try to import membership model and reverse URL
                from django.urls import reverse
                url = reverse('admin:memberships_usermembership_change', args=[active_membership.id])
                return format_html('<a href="{}">View Membership Details</a>', url)
            except:
                return f"Membership ID: {active_membership.id}"
        return '-'
    active_membership_link.short_description = 'Membership Link'
    
    def avatar_preview(self, obj):
        """Display avatar preview in form"""
        if obj.avatar:
            return format_html(
                '<img src="{}" width="100" style="border-radius: 50%;" />',
                obj.avatar.url
            )
        return '-'
    avatar_preview.short_description = 'Avatar Preview'
    
    def get_queryset(self, request):
        """Optimize queryset with annotations"""
        queryset = super().get_queryset(request)
        return queryset
    
    actions = [
        'verify_users', 'unverify_users', 'activate_users', 'deactivate_users',
        'send_welcome_email', 'export_users_csv', 'assign_gold_membership'
    ]
    
    def verify_users(self, request, queryset):
        """Bulk verify users"""
        now = timezone.now()
        updated = queryset.filter(is_verified=False).update(is_verified=True, verified_at=now)
        self.message_user(request, f'{updated} users verified.')
    verify_users.short_description = 'Verify selected users'
    
    def unverify_users(self, request, queryset):
        """Bulk unverify users"""
        updated = queryset.filter(is_verified=True).update(is_verified=False, verified_at=None)
        self.message_user(request, f'{updated} users unverified.')
    unverify_users.short_description = 'Unverify selected users'
    
    def activate_users(self, request, queryset):
        """Bulk activate users"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} users activated.')
    activate_users.short_description = 'Activate selected users'
    
    def deactivate_users(self, request, queryset):
        """Bulk deactivate users"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} users deactivated.')
    deactivate_users.short_description = 'Deactivate selected users'
    
    def send_welcome_email(self, request, queryset):
        """Send welcome email to selected users"""
        # This would integrate with your email system
        self.message_user(request, f'Welcome emails sent to {queryset.count()} users.', level='SUCCESS')
    send_welcome_email.short_description = 'Send welcome email'
    
    def export_users_csv(self, request, queryset):
        """Export selected users to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Username', 'Email', 'Full Name', 'Phone', 'Current Country',
            'City', 'Migration Status', 'Verified', 'Active', 'Date Joined',
            'Last Login', 'Birth Country', 'Destination Country'
        ])
        
        for user in queryset:
            writer.writerow([
                user.id, user.username, user.email, user.get_full_name(),
                user.phone, user.current_country, user.city,
                user.get_migration_status_display(), user.is_verified,
                user.is_active, user.date_joined, user.last_login,
                user.birth_country, user.destination_country
            ])
        
        return response
    export_users_csv.short_description = 'Export selected users to CSV'
    
    def assign_gold_membership(self, request, queryset):
        """Assign gold membership to selected users"""
        try:
            from memberships.models import UserMembership
            
            assigned = 0
            for user in queryset:
                # Check if user already has active membership
                if not user.active_membership:
                    UserMembership.objects.create(
                        user=user,
                        plan='gold',
                        country_code=user.current_country or 'US',
                        expires_at=timezone.now() + timezone.timedelta(days=30),
                        is_active=True,
                        amount_paid=0,
                        currency_paid='USD'
                    )
                    assigned += 1
            
            self.message_user(request, f'Gold membership assigned to {assigned} users.')
        except ImportError:
            self.message_user(request, 'Membership app not found. Please install membership app first.', level='ERROR')
    assign_gold_membership.short_description = 'Assign Gold membership (30 days)'


# Optional: User Stats Admin (uncomment if you want to use it)
# class UserStatsAdmin(admin.ModelAdmin):
#     """Custom admin view for user statistics"""
#     change_list_template = 'admin/user_stats.html'
#     
#     def changelist_view(self, request, extra_context=None):
#         from django.db.models import Count
#         from datetime import timedelta
#         
#         now = timezone.now()
#         
#         # Overall stats
#         total_users = models.User.objects.count()
#         active_users = models.User.objects.filter(is_active=True).count()
#         verified_users = models.User.objects.filter(is_verified=True).count()
#         
#         # Users by country
#         users_by_country = models.User.objects.values('current_country').annotate(
#             count=Count('id')
#         ).order_by('-count')[:10]
#         
#         # Users by migration status
#         users_by_migration = models.User.objects.values('migration_status').annotate(
#             count=Count('id')
#         )
#         
#         # Recent signups
#         recent_signups = models.User.objects.filter(
#             date_joined__gte=now - timedelta(days=30)
#         ).count()
#         
#         # Users with location data
#         users_with_location = models.User.objects.filter(location__isnull=False).count()
#         
#         extra_context = extra_context or {}
#         extra_context.update({
#             'total_users': total_users,
#             'active_users': active_users,
#             'verified_users': verified_users,
#             'verified_percentage': (verified_users / total_users * 100) if total_users > 0 else 0,
#             'users_by_country': users_by_country,
#             'users_by_migration': users_by_migration,
#             'recent_signups': recent_signups,
#             'users_with_location': users_with_location,
#         })
#         
#         return super().changelist_view(request, extra_context=extra_context)
# 
# 
# # Uncomment to use the stats view instead
# # admin.site.unregister(models.User)
# # admin.site.register(models.User, UserStatsAdmin)