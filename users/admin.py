# backend/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.gis import admin as gis_admin
from django.utils.html import format_html
from .models import User


@admin.register(User)
class UserAdmin(gis_admin.GISModelAdmin, BaseUserAdmin):
    """
    Custom admin interface for User model with ULID and PostGIS location.
    """
    
    # Fields to display in the list view
    list_display = (
        'id', 'username', 'email', 'phone', 'current_country', 
        'migration_status', 'is_verified', 'is_active', 'is_staff', 
        'created_at_display', 'location_preview'
    )
    
    # Fields that are clickable links
    list_display_links = ('id', 'username', 'email')
    
    # Filters in the sidebar
    list_filter = (
        'is_verified', 'is_active', 'is_staff', 'is_superuser',
        'migration_status', 'current_country', 'location_source',
        'created_at', 'verified_at'
    )
    
    # Searchable fields
    search_fields = (
        'id', 'username', 'email', 'phone', 'first_name', 'last_name',
        'current_country', 'destination_country', 'city'
    )
    
    # Fields that can be edited directly in the list view
    list_editable = ('is_verified', 'is_active')
    
    # Default ordering
    ordering = ('-created_at',)
    
    # Date hierarchy for navigation
    date_hierarchy = 'created_at'
    
    # Number of items per page
    list_per_page = 25
    
    # Fieldsets for the detail/edit form
    fieldsets = (
        # Basic Information
        ('Basic Information', {
            'fields': (
                'username', 'email', 'password', 'first_name', 'last_name',
            ),
            'classes': ('wide',),
        }),
        
        # Location Information
        ('Location Information', {
            'fields': (
                'birth_country', 'current_country', 'destination_country',
                'city', 'state_province', 'location', 'location_source',
            ),
            'classes': ('wide',),
            'description': 'Geographic information and GPS location'
        }),
        
        # Profile Information
        ('Profile Information', {
            'fields': (
                'phone', 'avatar', 'bio', 'migration_status',
            ),
            'classes': ('wide',),
        }),
        
        # Verification & Status
        ('Verification & Status', {
            'fields': (
                'is_verified', 'verified_at', 'is_active',
                'accepted_terms', 'accepted_terms_at',
            ),
            'classes': ('wide',),
        }),
        
        # Permissions
        ('Permissions', {
            'fields': (
                'is_staff', 'is_superuser', 'groups', 'user_permissions',
            ),
            'classes': ('wide',),
        }),
        
        # Important Dates
        ('Important Dates', {
            'fields': (
                'last_login', 'date_joined', 'created_at', 'updated_at',
            ),
            'classes': ('wide',),
        }),
    )
    
    # Fields that are read-only
    readonly_fields = (
        'id', 'created_at', 'updated_at', 'date_joined',
        'latitude_display', 'longitude_display', 'avatar_preview'
    )
    
    # Fields to include when adding a new user
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password1', 'password2',
                'first_name', 'last_name', 'current_country',
            ),
        }),
    )
    
    # Override fields to use custom widgets/attributes
    def get_fieldsets(self, request, obj=None):
        """Modify fieldsets based on whether we're adding or editing."""
        fieldsets = super().get_fieldsets(request, obj)
        
        if not obj:  # Adding a new user
            # Remove read-only fields from add form
            self.readonly_fields = ('id',)
        else:  # Editing existing user
            pass
            
        return fieldsets
    
    # Custom display methods
    def created_at_display(self, obj):
        """Display created_at in a readable format."""
        return obj.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_display.short_description = 'Created At'
    created_at_display.admin_order_field = 'created_at'
    
    def latitude_display(self, obj):
        """Display latitude if location exists."""
        return obj.latitude if obj.latitude else 'Not set'
    latitude_display.short_description = 'Latitude'
    
    def longitude_display(self, obj):
        """Display longitude if location exists."""
        return obj.longitude if obj.longitude else 'Not set'
    longitude_display.short_description = 'Longitude'
    
    def location_preview(self, obj):
        """Show a map preview of the location if available."""
        if obj.location and obj.latitude and obj.longitude:
            # Google Maps static image preview
            maps_url = f"https://maps.google.com/maps?q={obj.latitude},{obj.longitude}&z=10"
            return format_html(
                '<a href="{}" target="_blank">📍 View on Map</a>',
                maps_url
            )
        return 'No location set'
    location_preview.short_description = 'Map Preview'
    
    def avatar_preview(self, obj):
        """Display avatar thumbnail if exists."""
        if obj.avatar:
            return format_html(
                '<img src="{}" width="50" height="50" style="border-radius: 50%;" />',
                obj.avatar.url
            )
        return 'No avatar'
    avatar_preview.short_description = 'Avatar'
    
    # Actions for bulk operations
    actions = ['mark_as_verified', 'mark_as_unverified', 'export_selected']
    
    def mark_as_verified(self, request, queryset):
        """Bulk verify selected users."""
        from django.utils import timezone
        updated = queryset.update(is_verified=True, verified_at=timezone.now())
        self.message_user(request, f'{updated} users marked as verified.')
    mark_as_verified.short_description = 'Mark selected users as verified'
    
    def mark_as_unverified(self, request, queryset):
        """Bulk unverify selected users."""
        updated = queryset.update(is_verified=False, verified_at=None)
        self.message_user(request, f'{updated} users marked as unverified.')
    mark_as_unverified.short_description = 'Mark selected users as unverified'
    
    def export_selected(self, request, queryset):
        """Export selected users as CSV."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Username', 'Email', 'First Name', 'Last Name', 'Phone',
            'Current Country', 'Destination Country', 'City', 'Migration Status',
            'Is Verified', 'Is Active', 'Created At'
        ])
        
        for user in queryset:
            writer.writerow([
                user.id, user.username, user.email, user.first_name, user.last_name,
                user.phone, user.current_country, user.destination_country, user.city,
                user.migration_status, user.is_verified, user.is_active, user.created_at
            ])
        
        return response
    export_selected.short_description = 'Export selected users to CSV'
    
    # Save model with custom handling
    def save_model(self, request, obj, form, change):
        """Override save to handle verification timestamp."""
        if not change:  # New user
            obj.date_joined = obj.created_at
        
        # Auto-set verified_at when is_verified becomes True
        if obj.is_verified and not obj.verified_at:
            from django.utils import timezone
            obj.verified_at = timezone.now()
        elif not obj.is_verified:
            obj.verified_at = None
            
        super().save_model(request, obj, form, change)
    
    # Inline for related memberships (if you have a Membership model)
    # from .models import Membership
    # inlines = [MembershipInline]


# Optional: Register a simpler version for non-staff users
class SimpleUserAdmin(admin.ModelAdmin):
    """Simpler admin interface for non-superusers."""
    list_display = ('username', 'email', 'current_country', 'is_verified')
    search_fields = ('username', 'email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    def get_queryset(self, request):
        """Limit non-superusers to see only certain users."""
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # Non-superusers can only see their own record
            return qs.filter(id=request.user.id)
        return qs


# You can register multiple admin views for the same model
# admin.site.register(User, UserAdmin)  # Already done via @register decorator