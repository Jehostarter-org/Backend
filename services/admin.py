from django.contrib import admin
from django.utils import timezone
from .models import (
    ServiceRequest, AirportPickup, HomeInspection,
    ChaperoneService, JobApplicationAssistance,
    ServiceProviderProfile, MigrationSpecialist,
    MigrationSpecialistApplication, ServiceReview,
)
from notifications.models import Notification


@admin.register(MigrationSpecialistApplication)
class MigrationSpecialistApplicationAdmin(admin.ModelAdmin):
    list_display  = ['user', 'status', 'submitted_at', 'reviewed_at']
    list_filter   = ['status']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['submitted_at', 'reviewed_at', 'reviewed_by']
    actions = ['approve_applications', 'reject_applications']

    def approve_applications(self, request, queryset):
        for application in queryset.filter(status='pending'):
            # Update application status
            application.status      = 'approved'
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save()

            # Create or update the MigrationSpecialist profile
            MigrationSpecialist.objects.update_or_create(
                user=application.user,
                defaults={
                    'bio':              application.bio,
                    'qualifications':   application.qualifications,
                    'countries_served': application.countries_served,
                    'languages':        application.languages,
                    'hourly_rate':      application.hourly_rate,
                    'currency':         application.currency,
                    'is_verified':      True,
                    'is_available':     True,
                }
            )

            # Notify the applicant
            Notification.objects.create(
                recipient=application.user,
                notification_type='system',
                title='Your Migration Specialist application was approved!',
                message='Congratulations! You are now a verified Migration Specialist on Jehostarter.',
                link='/dashboard/specialist',
            )

        self.message_user(request, f'{queryset.count()} application(s) approved.')

    approve_applications.short_description = 'Approve selected applications'

    def reject_applications(self, request, queryset):
        # For rejections you'll want to set a reason — this is a simple version.
        # For a full rejection form, use a custom intermediate admin view.
        for application in queryset.filter(status='pending'):
            application.status      = 'rejected'
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.rejection_reason = 'Your application did not meet the current requirements.'
            application.save()

            Notification.objects.create(
                recipient=application.user,
                notification_type='system',
                title='Your Migration Specialist application was not approved',
                message=application.rejection_reason,
                link='/dashboard/specialist/apply',
            )

        self.message_user(request, f'{queryset.count()} application(s) rejected.')

    reject_applications.short_description = 'Reject selected applications'


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display  = ['id', 'service_type', 'requester', 'provider', 'status', 'city', 'country_code', 'created_at']
    list_filter   = ['service_type', 'status', 'country_code']
    search_fields = ['requester__email', 'provider__email', 'city']


@admin.register(ServiceProviderProfile)
class ServiceProviderProfileAdmin(admin.ModelAdmin):
    list_display  = ['user', 'service_type', 'city', 'country_code', 'is_active', 'registered_at']
    list_filter   = ['service_type', 'country_code', 'is_active']
    search_fields = ['user__email', 'city']


@admin.register(MigrationSpecialist)
class MigrationSpecialistAdmin(admin.ModelAdmin):
    list_display  = ['user', 'is_verified', 'is_available', 'rating', 'total_reviews']
    list_filter   = ['is_verified', 'is_available']
    search_fields = ['user__email']


admin.site.register(AirportPickup)
admin.site.register(HomeInspection)
admin.site.register(ChaperoneService)
admin.site.register(JobApplicationAssistance)
admin.site.register(ServiceReview)