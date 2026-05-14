from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin panel for the custom Jehostarter User model.
    Extends Django's built-in UserAdmin so password hashing,
    permission management, etc. all work out of the box.
    """

    # ── List view ─────────────────────────────────────────────────────────────
    list_display    = (
        'email', 'username', 'full_name', 'avatar_preview',
        'current_country', 'migration_status', 'membership_plan_display',
        'is_verified', 'is_active', 'is_staff', 'created_at',
    )
    list_filter     = (
        'is_active', 'is_staff', 'is_superuser', 'is_verified',
        'migration_status', 'birth_country', 'current_country',
        'destination_country', 'accepted_terms',
    )
    search_fields   = ('email', 'username', 'first_name', 'last_name', 'phone')
    ordering        = ('-created_at',)
    list_per_page   = 25
    date_hierarchy  = 'created_at'
    readonly_fields = (
        'id', 'created_at', 'updated_at',
        'accepted_terms_at', 'verified_at',
        'avatar_preview', 'currency_display', 'membership_plan_display',
    )

    # ── Detail view fieldsets ─────────────────────────────────────────────────
    fieldsets = (
        ('Account', {
            'fields': ('id', 'email', 'username', 'password'),
        }),
        ('Personal Info', {
            'fields': (
                'first_name', 'last_name', 'phone',
                'avatar', 'avatar_preview', 'bio',
            ),
        }),
        ('Location', {
            'fields': (
                'birth_country', 'current_country', 'destination_country',
                'city', 'state_province', 'currency_display',
            ),
        }),
        ('Migration', {
            'fields': ('migration_status',),
        }),
        ('Membership', {
            'fields': ('membership_plan_display',),
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_at'),
        }),
        ('Terms & Conditions', {
            'fields': ('accepted_terms', 'accepted_terms_at'),
        }),
        ('Permissions', {
            'classes': ('collapse',),
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions',
            ),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at', 'last_login', 'date_joined'),
        }),
    )

    # ── Add-user form fieldsets ───────────────────────────────────────────────
    add_fieldsets = (
        ('Credentials', {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
        ('Personal Info', {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'phone'),
        }),
        ('Location', {
            'classes': ('wide',),
            'fields': (
                'birth_country', 'current_country',
                'destination_country', 'city', 'state_province',
            ),
        }),
        ('Migration', {
            'classes': ('wide',),
            'fields': ('migration_status',),
        }),
    )

    # ── Computed display columns ──────────────────────────────────────────────
    @admin.display(description='Name')
    def full_name(self, obj):
        return obj.get_full_name() or '—'

    @admin.display(description='Avatar')
    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width:40px;height:40px;'
                'border-radius:50%;object-fit:cover;" />',
                obj.avatar.url,
            )
        return '—'

    @admin.display(description='Currency')
    def currency_display(self, obj):
        return obj.currency

    @admin.display(description='Membership')
    def membership_plan_display(self, obj):
        plan = obj.membership_plan
        colours = {'gold': '#b7950b', 'free': '#6b7280'}
        colour = colours.get(plan, '#6b7280')
        return format_html(
            '<span style="color:{};font-weight:600;text-transform:capitalize;">{}</span>',
            colour, plan,
        )