from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.gis import admin as gis_admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.admin import SimpleListFilter
from django.contrib import messages
from . import models


# ─── Filters ──────────────────────────────────────────────────────────────────

class MembershipStatusFilter(SimpleListFilter):
    title = 'Membership Plan'
    parameter_name = 'membership_plan'

    def lookups(self, request, model_admin):
        return [('free', 'Free'), ('silver', 'Silver'), ('gold', 'Gold')]

    def queryset(self, request, queryset):
        if self.value():
            from django.db.models import Exists, OuterRef
            from memberships.models import UserMembership
            active = UserMembership.objects.filter(
                user=OuterRef('pk'), is_active=True, plan=self.value()
            )
            return queryset.filter(Exists(active))
        return queryset


class VerificationStatusFilter(SimpleListFilter):
    title = 'Verification Status'
    parameter_name = 'verified'

    def lookups(self, request, model_admin):
        return [('verified', 'Verified'), ('unverified', 'Unverified')]

    def queryset(self, request, queryset):
        if self.value() == 'verified':
            return queryset.filter(is_verified=True)
        if self.value() == 'unverified':
            return queryset.filter(is_verified=False)
        return queryset


class MigrationStatusFilter(SimpleListFilter):
    title = 'Migration Status'
    parameter_name = 'migration_status'

    def lookups(self, request, model_admin):
        return models.User.MIGRATION_STATUS

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(migration_status=self.value())
        return queryset


class LocationSourceFilter(SimpleListFilter):
    title = 'Location Source'
    parameter_name = 'location_source'

    def lookups(self, request, model_admin):
        return models.User.LOCATION_SOURCE

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(location_source=self.value())
        return queryset


class OTPStatusFilter(SimpleListFilter):
    """Filter OTP codes by their current lifecycle state."""
    title = 'OTP Status'
    parameter_name = 'otp_status'

    def lookups(self, request, model_admin):
        return [
            ('active',  'Active (unused, not expired)'),
            ('expired', 'Expired'),
            ('used',    'Used'),
            ('locked',  'Locked (max attempts reached)'),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'active':
            return queryset.filter(used_at__isnull=True, expires_at__gt=now, attempts__lt=5)
        if self.value() == 'expired':
            return queryset.filter(used_at__isnull=True, expires_at__lte=now)
        if self.value() == 'used':
            return queryset.filter(used_at__isnull=False)
        if self.value() == 'locked':
            return queryset.filter(used_at__isnull=True, attempts__gte=5)
        return queryset


# ─── GIS base ─────────────────────────────────────────────────────────────────

class UserGeoAdmin(gis_admin.GISModelAdmin):
    gis_widget_kwargs = {
        'attrs': {'default_zoom': 5, 'default_lon': 0, 'default_lat': 0},
    }
    map_width = 600
    map_height = 400


# ─── User Admin ───────────────────────────────────────────────────────────────

@admin.register(models.User)
class UserAdmin(BaseUserAdmin, UserGeoAdmin):
    """
    Full admin for the custom User model.
    Actions: verify, unverify, activate, deactivate,
             resend OTP, reset OTP attempts,
             assign Silver / Gold membership, export CSV.
    """

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'phone', 'bio'),
        }),
        ('Location', {
            'fields': (
                'birth_country', 'current_country', 'destination_country',
                'city', 'state_province', 'location', 'location_source',
            ),
        }),
    )

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Information', {
            'fields': (
                'first_name', 'last_name', 'email', 'phone',
                'bio', 'avatar', 'avatar_preview',
            ),
        }),
        ('Location & Geography', {
            'fields': (
                'birth_country', 'current_country', 'destination_country',
                'city', 'state_province', 'location', 'location_source',
                'latitude', 'longitude',
            ),
        }),
        ('Migration Status', {
            'fields': ('migration_status',),
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_at'),
        }),
        ('Legal', {
            'fields': ('accepted_terms', 'accepted_terms_at'),
        }),
        ('Membership', {
            'fields': ('membership_plan_display', 'active_membership_link'),
            'classes': ('collapse',),
        }),
        ('Permissions', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions',
            ),
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at'),
        }),
    )

    list_display = [
        'avatar_thumbnail', 'user_info', 'email', 'current_location',
        'membership_badge', 'migration_status_badge', 'verification_badge',
        'active_status', 'date_joined_short',
    ]

    list_filter = [
        'is_active', 'is_staff', 'is_superuser', 'is_verified',
        VerificationStatusFilter, MembershipStatusFilter,
        MigrationStatusFilter, LocationSourceFilter,
        'current_country', 'destination_country',
        'date_joined', 'created_at',
    ]

    search_fields = [
        'username', 'email', 'first_name', 'last_name',
        'phone', 'city', 'state_province',
    ]

    readonly_fields = [
        'id', 'last_login', 'date_joined', 'created_at', 'updated_at',
        'latitude', 'longitude',
        'membership_plan_display', 'active_membership_link',
        'avatar_preview',
    ]

    ordering = ['-date_joined']
    list_per_page = 25
    map_width = 600
    map_height = 400

    # ── Actions ───────────────────────────────────────────────────────────────

    actions = [
        'verify_users',
        'unverify_users',
        'activate_users',
        'deactivate_users',
        'resend_verification_otp',
        'reset_otp_attempts',
        'assign_silver_membership',
        'assign_gold_membership',
        'export_users_csv',
    ]

    # -- Verification --

    def verify_users(self, request, queryset):
        """Manually verify selected users."""
        updated = queryset.filter(is_verified=False).update(
            is_verified=True, verified_at=timezone.now()
        )
        self.message_user(request, f'{updated} user(s) marked as verified.')
    verify_users.short_description = '✔ Verify selected users'

    def unverify_users(self, request, queryset):
        """Revoke email verification for selected users."""
        updated = queryset.filter(is_verified=True).update(
            is_verified=False, verified_at=None
        )
        self.message_user(request, f'{updated} user(s) unverified.')
    unverify_users.short_description = '✖ Unverify selected users'

    # -- Activation --

    def activate_users(self, request, queryset):
        """Re-activate deactivated accounts."""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} user(s) activated.')
    activate_users.short_description = '● Activate selected users'

    def deactivate_users(self, request, queryset):
        """Soft-delete accounts by marking them inactive."""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} user(s) deactivated.')
    deactivate_users.short_description = '○ Deactivate selected users'

    # -- OTP --

    def resend_verification_otp(self, request, queryset):
        """
        Generate a fresh OTP and email it to each selected unverified user.
        Skips already-verified accounts silently.
        """
        from .email_verification import send_verification_email
        sent = 0
        skipped = 0
        for user in queryset:
            if user.is_verified:
                skipped += 1
                continue
            try:
                send_verification_email(user)
                sent += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f'Could not send OTP to {user.email}: {exc}',
                    level=messages.WARNING,
                )
        if sent:
            self.message_user(request, f'Verification OTP sent to {sent} user(s).')
        if skipped:
            self.message_user(
                request,
                f'{skipped} user(s) skipped (already verified).',
                level=messages.WARNING,
            )
    resend_verification_otp.short_description = '📧 Resend verification OTP'

    def reset_otp_attempts(self, request, queryset):
        """
        Clear the failed-attempt counter on active OTP codes so a locked-out
        user can retry without needing a brand new code.
        """
        updated = (
            models.EmailVerificationCode.objects
            .filter(user__in=queryset, used_at__isnull=True, attempts__gt=0)
            .update(attempts=0)
        )
        self.message_user(
            request,
            f'Attempt counter reset on {updated} active OTP code(s).',
        )
    reset_otp_attempts.short_description = '🔄 Reset OTP attempt counters'

    # -- Membership --

    def _assign_membership(self, request, queryset, plan, label):
        try:
            from memberships.models import UserMembership
        except ImportError:
            self.message_user(request, 'Membership app not found.', level=messages.ERROR)
            return
        assigned = 0
        for user in queryset:
            if not user.active_membership:
                UserMembership.objects.create(
                    user=user,
                    plan=plan,
                    country_code=user.current_country or 'US',
                    expires_at=timezone.now() + timedelta(days=30),
                    is_active=True,
                    amount_paid=0,
                    currency_paid='USD',
                )
                assigned += 1
        self.message_user(
            request,
            f'{label} membership (30 days) assigned to {assigned} user(s). '
            f'{queryset.count() - assigned} skipped (already have active membership).',
        )

    def assign_silver_membership(self, request, queryset):
        self._assign_membership(request, queryset, 'silver', '🥈 Silver')
    assign_silver_membership.short_description = '🥈 Assign Silver membership (30 days)'

    def assign_gold_membership(self, request, queryset):
        self._assign_membership(request, queryset, 'gold', '🥇 Gold')
    assign_gold_membership.short_description = '🥇 Assign Gold membership (30 days)'

    # -- Export --

    def export_users_csv(self, request, queryset):
        """Download selected users as a CSV file."""
        import csv
        from django.http import HttpResponse
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Username', 'Email', 'Full Name', 'Phone',
            'Current Country', 'Birth Country', 'Destination Country',
            'City', 'State/Province', 'Migration Status',
            'Verified', 'Verified At',
            'Active', 'Terms Accepted', 'Terms Accepted At',
            'Date Joined', 'Last Login',
        ])
        for user in queryset:
            writer.writerow([
                user.id, user.username, user.email, user.get_full_name(),
                user.phone, user.current_country, user.birth_country,
                user.destination_country, user.city, user.state_province,
                user.get_migration_status_display(),
                user.is_verified, user.verified_at,
                user.is_active, user.accepted_terms, user.accepted_terms_at,
                user.date_joined, user.last_login,
            ])
        return response
    export_users_csv.short_description = '⬇ Export selected users to CSV'

    # ── Fieldset permission guard ──────────────────────────────────────────────

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        # Non-superuser staff cannot see or change permissions
        return [fs for fs in fieldsets if fs[0] != 'Permissions']

    # ── Display helpers ───────────────────────────────────────────────────────

    def avatar_thumbnail(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" width="40" height="40" '
                'style="border-radius:50%;object-fit:cover;" />',
                obj.avatar.url,
            )
        initials = (
            (obj.first_name[0] if obj.first_name else '') +
            (obj.last_name[0] if obj.last_name else '')
        ) or (obj.username[0].upper() if obj.username else 'U')
        return format_html(
            '<div style="width:40px;height:40px;background:#3498db;color:white;'
            'border-radius:50%;display:flex;align-items:center;'
            'justify-content:center;font-weight:bold;">{}</div>',
            initials,
        )
    avatar_thumbnail.short_description = 'Avatar'

    def user_info(self, obj):
        return format_html(
            '<div><strong><a href="{}">{}</a></strong></div>'
            '<div style="color:#666;font-size:11px;">@{}</div>'
            '<div style="color:#999;font-size:10px;">ID: <code>{}</code></div>',
            reverse('admin:users_user_change', args=[obj.id]),
            obj.get_full_name() or obj.username,
            obj.username,
            obj.id[:8],
        )
    user_info.short_description = 'User'

    def current_location(self, obj):
        parts = [p for p in [obj.city, obj.state_province, obj.current_country] if p]
        if parts:
            text = ', '.join(parts)
            if obj.latitude is not None and obj.longitude is not None:
                coords = f'{float(obj.latitude):.4f}, {float(obj.longitude):.4f}'
                return format_html(
                    '{}<br/><span style="color:#999;font-size:10px;">📍 {}</span>',
                    text, coords,
                )
            return text
        return mark_safe('<span style="color:#999;">Not set</span>')
    current_location.short_description = 'Location'

    def membership_badge(self, obj):
        plan = obj.membership_plan
        colors = {'free': '#95a5a6', 'silver': '#bdc3c7', 'gold': '#f39c12'}
        icons  = {'free': '🆓', 'silver': '🥈', 'gold': '🥇'}
        color  = colors.get(plan, '#95a5a6')
        icon   = icons.get(plan, '📋')
        text_color = 'black' if plan == 'silver' else 'white'
        return format_html(
            '<span style="background:{};color:{};padding:3px 8px;'
            'border-radius:12px;font-size:11px;font-weight:bold;">{} {}</span>',
            color, text_color, icon, plan.upper(),
        )
    membership_badge.short_description = 'Plan'

    def migration_status_badge(self, obj):
        icons = {
            'planning': '✈️', 'in_transit': '🚗',
            'arrived': '🏠', 'settled': '✅',
        }
        icon  = icons.get(obj.migration_status, '📌')
        label = dict(models.User.MIGRATION_STATUS).get(obj.migration_status, 'Not set')
        return format_html('{} {}', icon, label)
    migration_status_badge.short_description = 'Migration'

    def verification_badge(self, obj):
        if obj.is_verified:
            date = obj.verified_at.strftime('%Y-%m-%d') if obj.verified_at else ''
            extra = (
                f'<br/><span style="color:#999;font-size:10px;">{date}</span>'
                if date else ''
            )
            return mark_safe(f'<span style="color:#27ae60;">✓ Verified</span>{extra}')
        return mark_safe('<span style="color:#e74c3c;">✗ Unverified</span>')
    verification_badge.short_description = 'Verified'

    def active_status(self, obj):
        if obj.is_active:
            return mark_safe('<span style="color:#27ae60;">● Active</span>')
        return mark_safe('<span style="color:#e74c3c;">● Inactive</span>')
    active_status.short_description = 'Status'

    def date_joined_short(self, obj):
        return obj.date_joined.strftime('%Y-%m-%d')
    date_joined_short.short_description = 'Joined'

    def membership_plan_display(self, obj):
        plan = obj.membership_plan
        m    = obj.active_membership
        if m:
            if m.expires_at > timezone.now():
                days = (m.expires_at - timezone.now()).days
                return format_html(
                    '<strong>{}</strong><br/>Expires: {}<br/>'
                    '<span style="color:#666;">{} days left</span>',
                    plan.upper(), m.expires_at.strftime('%Y-%m-%d'), days,
                )
            return format_html(
                '<strong>{}</strong><br/><span style="color:#e74c3c;">Expired</span>',
                plan.upper(),
            )
        return mark_safe('<span style="color:#999;">Free Plan</span>')
    membership_plan_display.short_description = 'Current Membership'

    def active_membership_link(self, obj):
        m = obj.active_membership
        if m:
            try:
                url = reverse('admin:memberships_usermembership_change', args=[m.id])
                return format_html('<a href="{}">View Membership Details</a>', url)
            except Exception:
                return f'Membership ID: {m.id}'
        return '—'
    active_membership_link.short_description = 'Membership Link'

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" width="100" style="border-radius:50%;" />',
                obj.avatar.url,
            )
        return '—'
    avatar_preview.short_description = 'Avatar Preview'



# ─── EmailVerificationCode Admin ──────────────────────────────────────────────

@admin.register(models.EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    """
    Admin for OTP codes.  Admins can:
      • See all codes with live status (active / expired / used / locked)
      • Filter by status, date
      • Reset attempt counters on locked codes without issuing a new OTP
      • Invalidate active codes (force user to request a new one)
      • Delete stale codes in bulk to keep the table clean
    """

    list_display = [
        'user_link', 'user_email', 'status_badge',
        'attempts_display', 'expires_at', 'created_at',
    ]
    list_filter   = [OTPStatusFilter, 'created_at', 'expires_at']
    search_fields = ['user__email', 'user__username']
    readonly_fields = [
        'id', 'user', 'code_hash',
        'expires_at', 'attempts', 'max_attempts',
        'used_at', 'created_at',
        'status_badge', 'is_expired_display', 'is_used_display',
    ]
    ordering = ['-created_at']
    list_per_page = 30

    fieldsets = (
        ('Code Info', {
            'fields': ('id', 'user', 'code_hash'),
        }),
        ('Status', {
            'fields': (
                'status_badge', 'is_expired_display', 'is_used_display',
                'attempts', 'max_attempts', 'used_at', 'expires_at',
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
        }),
    )

    actions = ['reset_attempts', 'invalidate_codes', 'delete_stale']

    # ── Display helpers ───────────────────────────────────────────────────────

    def user_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'

    def status_badge(self, obj):
        now = timezone.now()
        if obj.used_at:
            return mark_safe('<span style="color:#27ae60;">✓ Used</span>')
        if now >= obj.expires_at:
            return mark_safe('<span style="color:#e74c3c;">⏰ Expired</span>')
        if obj.attempts >= obj.max_attempts:
            return mark_safe('<span style="color:#e67e22;">🔒 Locked</span>')
        remaining = obj.max_attempts - obj.attempts
        return format_html(
            '<span style="color:#2980b9;">🔵 Active ({} attempt(s) left)</span>',
            remaining,
        )
    status_badge.short_description = 'Status'

    def attempts_display(self, obj):
        color = '#e74c3c' if obj.attempts >= obj.max_attempts else '#333'
        return format_html(
            '<span style="color:{};">{} / {}</span>',
            color, obj.attempts, obj.max_attempts,
        )
    attempts_display.short_description = 'Attempts'

    def is_expired_display(self, obj):
        return obj.is_expired
    is_expired_display.short_description = 'Expired?'
    is_expired_display.boolean = True

    def is_used_display(self, obj):
        return obj.is_used
    is_used_display.short_description = 'Used?'
    is_used_display.boolean = True

    # ── Actions ───────────────────────────────────────────────────────────


@admin.register(models.PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """
    Admin for password-reset tokens.
    Lets admins inspect, invalidate, and clean up stale tokens.
    """

    list_display = [
        'user_link', 'user_email', 'status_badge',
        'expires_at', 'created_at',
    ]
    list_filter = ['created_at', 'expires_at']
    search_fields = ['user__email', 'user__username', 'token_hash']
    readonly_fields = [
        'id', 'user', 'token_hash',
        'expires_at', 'used_at', 'created_at',
        'status_badge',
    ]
    ordering = ['-created_at']
    list_per_page = 30

    fieldsets = (
        ('Token Info', {
            'fields': ('id', 'user', 'token_hash'),
        }),
        ('Status', {
            'fields': ('status_badge', 'expires_at', 'used_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
        }),
    )

    actions = ['invalidate_tokens', 'delete_stale_tokens']

    # ── Display helpers ───────────────────────────────────────────────────

    def user_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'

    def status_badge(self, obj):
        now = timezone.now()
        if obj.used_at:
            return mark_safe('<span style="color:#27ae60;">✓ Used</span>')
        if now >= obj.expires_at:
            return mark_safe('<span style="color:#e74c3c;">⏰ Expired</span>')
        return mark_safe('<span style="color:#2980b9;">🔵 Active</span>')
    status_badge.short_description = 'Status'

    # ── Actions ───────────────────────────────────────────────────────────

    def invalidate_tokens(self, request, queryset):
        """Mark tokens as used so they can no longer be redeemed."""
        updated = queryset.filter(used_at__isnull=True).update(used_at=timezone.now())
        self.message_user(request, f'{updated} token(s) invalidated.')
    invalidate_tokens.short_description = '🚫 Invalidate selected tokens'

    def delete_stale_tokens(self, request, queryset):
        """Remove expired and used tokens."""
        now = timezone.now()
        stale = queryset.filter(expires_at__lte=now) | queryset.filter(used_at__isnull=False)
        count, _ = stale.delete()
        self.message_user(request, f'{count} stale token(s) deleted.')
    delete_stale_tokens.short_description = '🗑 Delete expired / used tokens'

    def reset_attempts(self, request, queryset):
        """Reset attempt counter — lets a locked user retry the same code."""
        updated = queryset.filter(used_at__isnull=True).update(attempts=0)
        self.message_user(request, f'Attempt counter reset on {updated} code(s).')
    reset_attempts.short_description = '🔄 Reset attempt counters'

    def invalidate_codes(self, request, queryset):
        """Mark selected codes as used so the user must request a fresh OTP."""
        updated = queryset.filter(used_at__isnull=True).update(used_at=timezone.now())
        self.message_user(request, f'{updated} code(s) invalidated.')
    invalidate_codes.short_description = '🚫 Invalidate selected codes'

    def delete_stale(self, request, queryset):
        """Remove expired and used codes from the database."""
        now = timezone.now()
        stale = queryset.filter(expires_at__lte=now) | queryset.filter(used_at__isnull=False)
        count, _ = stale.delete()
        self.message_user(request, f'{count} stale code(s) deleted.')
    delete_stale.short_description = '🗑 Delete expired / used codes'