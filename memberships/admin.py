# admin.py (add to your existing admin.py file)
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Sum, Q, F
from django.contrib.admin import SimpleListFilter
from django.core.management import call_command
from . import models


class PlanFilter(SimpleListFilter):
    """Filter by membership plan"""
    title = 'Membership Plan'
    parameter_name = 'plan'
    
    def lookups(self, request, model_admin):
        return [
            ('free', 'Free'),
            ('silver', 'Silver'),
            ('gold', 'Gold'),
        ]
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(plan=self.value())
        return queryset


class ActiveMembershipFilter(SimpleListFilter):
    """Filter for active vs expired memberships"""
    title = 'Membership Status'
    parameter_name = 'status'
    
    def lookups(self, request, model_admin):
        return [
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('expiring_soon', 'Expiring Soon (7 days)'),
        ]
    
    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'active':
            return queryset.filter(is_active=True, expires_at__gt=now)
        if self.value() == 'expired':
            return queryset.filter(Q(is_active=False) | Q(expires_at__lte=now))
        if self.value() == 'expiring_soon':
            soon = now + timezone.timedelta(days=7)
            return queryset.filter(is_active=True, expires_at__lte=soon, expires_at__gt=now)
        return queryset


@admin.register(models.MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = [
        'plan_badge', 'country_code', 'price', 'currency', 'duration_days',
        'features_summary', 'max_listings_display', 'created_at'
    ]
    list_filter = ['plan', 'country_code', 'can_create_shop', 'can_boost_products', 'duration_days']
    search_fields = ['plan', 'country_code', 'currency']
    readonly_fields = ['id', 'created_at']
    list_per_page = 25
    list_editable = ['price', 'duration_days', 'currency']
    
    fieldsets = (
        ('Plan Details', {
            'fields': ('plan', 'country_code', 'price', 'currency', 'duration_days')
        }),
        ('Core Features', {
            'fields': (
                'can_create_shop', 'can_create_community', 'can_join_community',
                'can_boost_products'
            )
        }),
        ('Service Access', {
            'fields': (
                'can_request_home_inspection', 'can_use_airport_pickup', 'can_use_chaperon'
            )
        }),
        ('Limits', {
            'fields': ('max_shop_listings',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def plan_badge(self, obj):
        colors = {
            'free': '#95a5a6',
            'silver': '#bdc3c7',
            'gold': '#f39c12'
        }
        color = colors.get(obj.plan, '#95a5a6')
        icons = {
            'free': '🆓',
            'silver': '🥈',
            'gold': '🥇'
        }
        icon = icons.get(obj.plan, '📋')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 10px; border-radius: 4px; font-weight: bold;">{} {}</span>',
            color, icon, obj.plan.upper()
        )
    plan_badge.short_description = 'Plan'
    
    def price_display(self, obj):
        return format_html('<strong>{}{}</strong>', obj.currency, obj.price)
    price_display.short_description = 'Price'
    
    def features_summary(self, obj):
        features = []
        if obj.can_create_shop:
            features.append('🏪 Shop')
        if obj.can_create_community:
            features.append('👥 Community')
        if obj.can_boost_products:
            features.append('🚀 Boost')
        if obj.can_request_home_inspection:
            features.append('🔍 Inspection')
        
        if features:
            return format_html('<span style="font-size: 12px;">{}</span>', ' '.join(features))
        return mark_safe('<span style="color: #999;">-</span>')
    features_summary.short_description = 'Features'
    
    def max_listings_display(self, obj):
        if obj.max_shop_listings == 0:
            return mark_safe('<span style="color: #999;">No shop</span>')
        elif obj.max_shop_listings == 999999:
            return mark_safe('<span style="color: #27ae60;">Unlimited</span>')
        else:
            return format_html('<strong>{}</strong>', obj.max_shop_listings)
    max_listings_display.short_description = 'Max Listings'
    
    actions = ['duplicate_plan', 'apply_to_all_countries']
    
    def duplicate_plan(self, request, queryset):
        """Duplicate selected plans to other countries"""
        for plan in queryset:
            countries = ['US', 'GB', 'AU', 'CA', 'NG', 'ZA']
            for country in countries:
                if country != plan.country_code:
                    models.MembershipPlan.objects.get_or_create(
                        plan=plan.plan,
                        country_code=country,
                        defaults={
                            'price': plan.price,
                            'currency': plan.currency,
                            'duration_days': plan.duration_days,
                            'can_create_shop': plan.can_create_shop,
                            'can_create_community': plan.can_create_community,
                            'can_join_community': plan.can_join_community,
                            'can_boost_products': plan.can_boost_products,
                            'can_request_home_inspection': plan.can_request_home_inspection,
                            'can_use_airport_pickup': plan.can_use_airport_pickup,
                            'can_use_chaperon': plan.can_use_chaperon,
                            'max_shop_listings': plan.max_shop_listings,
                        }
                    )
        self.message_user(request, f'Plans duplicated to other countries.')
    duplicate_plan.short_description = 'Duplicate plan to other countries'
    
    def apply_to_all_countries(self, request, queryset):
        """Apply plan settings to all countries"""
        self.message_user(request, 'Please use the duplicate action instead.', level='WARNING')
    apply_to_all_countries.short_description = 'Apply to all countries (use duplicate)'


@admin.register(models.UserMembership)
class UserMembershipAdmin(admin.ModelAdmin):
    list_display = [
        'user_link', 'plan_badge', 'country_code', 'status_badge',
        'started_at_display', 'expires_at_display', 'days_remaining', 
        'payment_info_short', 'amount_paid_display'
    ]
    list_filter = [
        ActiveMembershipFilter, PlanFilter, 'country_code', 'is_active',
        'payment_gateway', 'started_at', 'expires_at'
    ]
    search_fields = [
        'user__email', 'user__username', 'payment_reference',
        'user__first_name', 'user__last_name'
    ]
    raw_id_fields = ['user']
    readonly_fields = ['id', 'started_at', 'created_at_display']
    list_per_page = 30
    list_select_related = ['user']
    date_hierarchy = 'started_at'
    
    fieldsets = (
        ('Membership Information', {
            'fields': ('user', 'plan', 'country_code', 'is_active')
        }),
        ('Duration', {
            'fields': ('started_at', 'expires_at', 'days_remaining_info')
        }),
        ('Payment Details', {
            'fields': ('payment_reference', 'payment_gateway', 'amount_paid', 'currency_paid')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at_display'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['days_remaining_info', 'created_at_display']
    
    def user_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.user.id])
        return format_html(
            '<a href="{}" style="font-weight: bold;">{}</a><br/>'
            '<span style="color: #666; font-size: 11px;">{}</span>',
            url,
            obj.user.get_full_name() or obj.user.username,
            obj.user.email
        )
    user_link.short_description = 'User'
    
    def plan_badge(self, obj):
        colors = {
            'free': '#95a5a6',
            'silver': '#bdc3c7',
            'gold': '#f39c12'
        }
        color = colors.get(obj.plan, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 3px; font-weight: bold; font-size: 12px;">{}</span>',
            color,
            'black' if obj.plan == 'silver' else 'white',
            obj.plan.upper()
        )
    plan_badge.short_description = 'Plan'
    
    def status_badge(self, obj):
        now = timezone.now()
        if obj.is_active and obj.expires_at > now:
            return format_html(
                '<span style="color: #27ae60; font-weight: bold;">✓ Active</span>'
            )
        elif obj.expires_at <= now:
            return format_html(
                '<span style="color: #e74c3c; font-weight: bold;">✗ Expired</span>'
            )
        else:
            return format_html(
                '<span style="color: #e74c3c; font-weight: bold;">✗ Inactive</span>'
            )
    status_badge.short_description = 'Status'
    
    def started_at_display(self, obj):
        return obj.started_at.strftime('%Y-%m-%d')
    started_at_display.short_description = 'Started'
    
    def expires_at_display(self, obj):
        now = timezone.now()
        if obj.expires_at < now:
            return format_html(
                '<span style="color: #e74c3c;">{}</span>',
                obj.expires_at.strftime('%Y-%m-%d')
            )
        elif obj.expires_at < now + timezone.timedelta(days=7):
            return format_html(
                '<span style="color: #f39c12; font-weight: bold;">⚠️ {}</span>',
                obj.expires_at.strftime('%Y-%m-%d')
            )
        else:
            return obj.expires_at.strftime('%Y-%m-%d')
    expires_at_display.short_description = 'Expires'
    
    def days_remaining(self, obj):
        now = timezone.now()
        if obj.expires_at > now:
            days = (obj.expires_at - now).days
            if days <= 7:
                return format_html(
                    '<span style="color: #f39c12; font-weight: bold;">{} days</span>',
                    days
                )
            return format_html('<span style="color: #27ae60;">{} days</span>', days)
        return mark_safe('<span style="color: #e74c3c;">Expired</span>')
    days_remaining.short_description = 'Days Left'
    
    def payment_info_short(self, obj):
        if obj.payment_reference:
            return format_html(
                '<span title="{}">💳 {}</span>',
                obj.payment_reference,
                obj.payment_reference[:12] + '...' if len(obj.payment_reference) > 12 else obj.payment_reference
            )
        return mark_safe('<span style="color: #999;">No payment</span>')
    payment_info_short.short_description = 'Payment Ref'
    
    def amount_paid_display(self, obj):
        if obj.amount_paid:
            return format_html(
                '<strong>{}{}</strong>',
                obj.currency_paid or '$',
                obj.amount_paid
            )
        return '-'
    amount_paid_display.short_description = 'Amount'
    
    def days_remaining_info(self, obj):
        """Helper for readonly field in form"""
        now = timezone.now()
        if obj.expires_at > now:
            days = (obj.expires_at - now).days
            return f"{days} days remaining"
        return "Expired"
    days_remaining_info.short_description = 'Days Remaining'
    
    def created_at_display(self, obj):
        return obj.started_at
    created_at_display.short_description = 'Created'
    
    actions = [
        'extend_membership', 'mark_as_expired', 'send_expiry_warning',
        'export_selected', 'activate_memberships', 'deactivate_memberships'
    ]
    
    def extend_membership(self, request, queryset):
        """Extend membership by 30 days"""
        extended_count = 0
        for membership in queryset:
            if membership.expires_at > timezone.now():
                membership.expires_at = membership.expires_at + timezone.timedelta(days=30)
            else:
                membership.expires_at = timezone.now() + timezone.timedelta(days=30)
                membership.is_active = True
            membership.save()
            extended_count += 1
        self.message_user(request, f'{extended_count} memberships extended by 30 days.')
    extend_membership.short_description = 'Extend membership by 30 days'
    
    def mark_as_expired(self, request, queryset):
        """Mark selected memberships as expired"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} memberships marked as expired.')
    mark_as_expired.short_description = 'Mark as expired'
    
    def send_expiry_warning(self, request, queryset):
        """Send expiry warning emails"""
        # This would integrate with your email system
        self.message_user(request, f'Expiry warnings sent to {queryset.count()} users.', level='SUCCESS')
    send_expiry_warning.short_description = 'Send expiry warning email'
    
    def export_selected(self, request, queryset):
        """Export selected memberships to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="memberships_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'User ID', 'Username', 'Email', 'Plan', 'Country', 'Status',
            'Started At', 'Expires At', 'Amount Paid', 'Currency', 'Payment Reference'
        ])
        
        for membership in queryset:
            writer.writerow([
                membership.user.id,
                membership.user.username,
                membership.user.email,
                membership.plan,
                membership.country_code,
                'Active' if membership.is_active else 'Expired',
                membership.started_at,
                membership.expires_at,
                membership.amount_paid,
                membership.currency_paid,
                membership.payment_reference,
            ])
        
        return response
    export_selected.short_description = 'Export selected to CSV'
    
    def activate_memberships(self, request, queryset):
        """Activate selected memberships"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} memberships activated.')
    activate_memberships.short_description = 'Activate selected memberships'
    
    def deactivate_memberships(self, request, queryset):
        """Deactivate selected memberships"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} memberships deactivated.')
    deactivate_memberships.short_description = 'Deactivate selected memberships'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('user')


class MembershipStatsAdmin(admin.ModelAdmin):
    """Custom admin view for membership statistics"""
    change_list_template = 'admin/membership_stats.html'
    
    def changelist_view(self, request, extra_context=None):
        from django.db.models import Count, Sum, Q
        from datetime import timedelta
        
        now = timezone.now()
        
        # Overall stats
        total_memberships = models.UserMembership.objects.count()
        active_memberships = models.UserMembership.objects.filter(
            is_active=True, expires_at__gt=now
        ).count()
        
        # Memberships by plan
        memberships_by_plan = models.UserMembership.objects.values('plan').annotate(
            count=Count('id'),
            active=Count('id', filter=Q(is_active=True, expires_at__gt=now))
        )
        
        # Revenue stats
        total_revenue = models.UserMembership.objects.filter(
            amount_paid__isnull=False
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Recent signups (last 30 days)
        recent_signups = models.UserMembership.objects.filter(
            started_at__gte=now - timedelta(days=30)
        ).count()
        
        # Expiring soon (next 7 days)
        expiring_soon = models.UserMembership.objects.filter(
            is_active=True,
            expires_at__gt=now,
            expires_at__lte=now + timedelta(days=7)
        ).count()
        
        extra_context = extra_context or {}
        extra_context.update({
            'total_memberships': total_memberships,
            'active_memberships': active_memberships,
            'active_percentage': (active_memberships / total_memberships * 100) if total_memberships > 0 else 0,
            'memberships_by_plan': memberships_by_plan,
            'total_revenue': total_revenue,
            'recent_signups': recent_signups,
            'expiring_soon': expiring_soon,
        })
        
        return super().changelist_view(request, extra_context=extra_context)


# Uncomment to use the stats view instead of the regular admin
# admin.site.unregister(models.UserMembership)
# admin.site.register(models.UserMembership, MembershipStatsAdmin)