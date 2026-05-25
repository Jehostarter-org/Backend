from ulid import ULID
from django.db import models
from django.conf import settings


def generate_ulid():
    return str(ULID())


class ServiceRequest(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    SERVICE_TYPES = [
        ('airport_pickup',       'Airport Pickup'),
        ('home_inspection',      'Home Inspection & Check'),
        ('job_application',      'Job Application Assistance'),
        ('chaperon',             'Chaperon Services'),
        ('migration_specialist', 'Migration Specialist'),
    ]
    STATUS = [
        ('pending',     'Pending'),
        ('accepted',    'Accepted'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
    ]

    requester    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='service_requests')
    provider     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_provisions')
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPES)
    description  = models.TextField()
    country_code = models.CharField(max_length=2)
    city         = models.CharField(max_length=100, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status       = models.CharField(max_length=20, choices=STATUS, default='pending')
    price        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency     = models.CharField(max_length=3, blank=True)
    notes        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_service_type_display()} – {self.requester}"


class AirportPickup(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    service_request  = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='airport_pickup_details')
    flight_number    = models.CharField(max_length=20)
    arrival_datetime = models.DateTimeField()
    airport          = models.CharField(max_length=200)
    terminal         = models.CharField(max_length=50, blank=True)
    num_passengers   = models.PositiveIntegerField(default=1)
    num_bags         = models.PositiveIntegerField(default=1)
    special_requests = models.TextField(blank=True)
    driver           = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pickup_jobs'
    )

    class Meta:
        db_table = 'airport_pickups'

    def __str__(self):
        return f"Pickup – {self.flight_number} @ {self.airport}"


class HomeInspection(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    service_request  = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='home_inspection_details')
    property_address = models.TextField()
    property_type    = models.CharField(max_length=50, blank=True)
    inspection_date  = models.DateField()
    checklist_items  = models.JSONField(default=list, blank=True)
    inspector        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inspection_jobs'
    )
    report       = models.FileField(upload_to='inspection_reports/', null=True, blank=True)
    report_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'home_inspections'

    def __str__(self):
        return f"Inspection – {self.property_address}"


class ChaperoneService(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    HELP_TYPES = [
        ('sim_card',     'SIM Card Registration'),
        ('tax_file',     'Tax File Number (TFN)'),
        ('registration', 'General Registration'),
        ('translation',  'Translation Service'),
        ('bank_account', 'Bank Account Opening'),
        ('other',        'Other'),
    ]

    service_request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='chaperone_details')
    help_type       = models.CharField(max_length=20, choices=HELP_TYPES)
    location        = models.CharField(max_length=200, blank=True)
    chaperone       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chaperone_jobs'
    )

    class Meta:
        db_table = 'chaperone_services'


class JobApplicationAssistance(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    service_request   = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='job_application_details')
    job_title         = models.CharField(max_length=200, blank=True)
    industry          = models.CharField(max_length=100, blank=True)
    cv_file           = models.FileField(upload_to='cvs/', null=True, blank=True)
    external_job_link = models.URLField(blank=True)
    specialist        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='job_assistance_jobs'
    )

    class Meta:
        db_table = 'job_application_assistance'


class ServiceProviderProfile(models.Model):
    """
    A user registers for one or more service types they want to offer.
    Each registration is a separate row — one profile per service type per user.
    Location is city-level: a Lagos driver only sees Lagos pickups.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    SERVICE_TYPES = [
        ('airport_pickup',  'Driver'),
        ('home_inspection', 'Home Inspector'),
        ('chaperon',        'Chaperone'),
        ('job_application', 'Job Application Assistant'),
    ]
    # Note: migration_specialist is excluded here — it has its own application flow

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='provider_profiles')
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPES)
    country_code = models.CharField(max_length=2)
    city         = models.CharField(max_length=100)  # strict city-level matching
    bio          = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'service_provider_profiles'
        unique_together = ('user', 'service_type')

    def __str__(self):
        return f"{self.user} – {self.get_service_type_display()} in {self.city}"


class MigrationSpecialist(models.Model):
    """
    Verified specialist profile — only created after admin approves application.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    user             = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='specialist_profile')
    bio              = models.TextField()
    qualifications   = models.TextField(blank=True)
    countries_served = models.JSONField(default=list)
    languages        = models.JSONField(default=list)
    hourly_rate      = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    currency         = models.CharField(max_length=3, blank=True)
    is_verified      = models.BooleanField(default=False)
    is_available     = models.BooleanField(default=True)
    rating           = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews    = models.PositiveIntegerField(default=0)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'migration_specialists'

    def __str__(self):
        return f"Specialist – {self.user}"


class MigrationSpecialistApplication(models.Model):
    """
    A user applies to become a migration specialist.
    Admin reviews and approves or rejects.
    On approval, a MigrationSpecialist profile is automatically created.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    STATUS = [
        ('pending',  'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user             = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='specialist_application')
    bio              = models.TextField()
    qualifications   = models.TextField()
    countries_served = models.JSONField(default=list)
    languages        = models.JSONField(default=list)
    hourly_rate      = models.DecimalField(max_digits=8, decimal_places=2)
    currency         = models.CharField(max_length=3)

    status           = models.CharField(max_length=10, choices=STATUS, default='pending')
    rejection_reason = models.TextField(blank=True)
    reviewed_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_applications'
    )
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'migration_specialist_applications'

    def __str__(self):
        return f"Application – {self.user} ({self.status})"


class ServiceReview(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    service_request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='review')
    reviewer        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_given')
    rating          = models.PositiveSmallIntegerField()
    comment         = models.TextField(blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'service_reviews'

    def __str__(self):
        return f"{self.rating}★ – {self.service_request}"
