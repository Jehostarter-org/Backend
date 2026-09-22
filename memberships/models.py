from ulid import ULID
from django.db import models
from django.conf import settings


def generate_ulid():
    return str(ULID())


PLAN_CHOICES = [('free', 'Free'), ('silver', 'Silver'), ('gold', 'Gold')]


class MembershipPlan(models.Model):
    """
    Stores the price & features of each plan per country.
    e.g. Gold in Nigeria = NGN 5000, Gold in Australia = AUD 29
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    plan          = models.CharField(max_length=10, choices=PLAN_CHOICES)
    country_code  = models.CharField(max_length=2)
    price         = models.DecimalField(max_digits=10, decimal_places=2)
    currency      = models.CharField(max_length=3)
    duration_days = models.PositiveIntegerField(default=30)

    # Feature flags per plan
    can_create_shop             = models.BooleanField(default=False)
    can_create_community        = models.BooleanField(default=False)
    can_join_community          = models.BooleanField(default=False)
    can_boost_products          = models.BooleanField(default=False)
    can_request_home_inspection = models.BooleanField(default=False)
    can_use_airport_pickup      = models.BooleanField(default=True)
    can_use_chaperon            = models.BooleanField(default=True)
    max_shop_listings           = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'membership_plans'
        unique_together = ('plan', 'country_code')

    def __str__(self):
        return f"{self.plan} – {self.country_code} ({self.currency} {self.price})"


class UserMembership(models.Model):
    """Active or past membership subscription for a user."""
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    plan         = models.CharField(max_length=10, choices=PLAN_CHOICES)
    country_code = models.CharField(max_length=2)
    started_at   = models.DateTimeField(auto_now_add=True)
    expires_at   = models.DateTimeField()
    is_active    = models.BooleanField(default=True)

    # Payment tracking
    payment_reference = models.CharField(max_length=200, blank=True)
    payment_gateway   = models.CharField(max_length=50, blank=True)
    amount_paid       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency_paid     = models.CharField(max_length=3, blank=True)

    class Meta:
        db_table = 'user_memberships'
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user} – {self.plan} ({'active' if self.is_active else 'expired'})"


class EligibilityCheck(models.Model):
    PATHWAY_CHOICES = [
        ('a', 'Already in Destination Country'),
        ('b', 'Still in Home Country'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('approved', 'Approved'),
        ('conditionally_approved', 'Conditionally Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='eligibility_checks')
    pathway = models.CharField(max_length=1, choices=PATHWAY_CHOICES)
    status = models.CharField(max_length=22, choices=STATUS_CHOICES, default='pending')

    # Pathway A fields
    visa_expiry = models.DateField(null=True, blank=True)

    # Pathway B fields
    passport_expiry = models.DateField(null=True, blank=True)
    migration_doc_type = models.CharField(max_length=20, blank=True)

    # Common fields
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    destination_country = models.CharField(max_length=2, blank=True)
    destination_city = models.CharField(max_length=100, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    # Admin review fields
    rejection_reason = models.TextField(blank=True, default='')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eligibility_checks'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} – Pathway {self.pathway.upper()} ({self.status})"


class EligibilityDocument(models.Model):
    DOCUMENT_TYPES = [
        ('visa_passport_page', 'Visa Passport Page'),
        ('vevo_check', 'VEVO Check'),
        ('payslip', 'Payslip'),
        ('bank_statement', 'Bank Statement'),
        ('address_proof', 'Address Proof'),
        ('passport', 'Passport'),
        ('migration_intent', 'Migration Intent'),
    ]

    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    eligibility_check = models.ForeignKey(EligibilityCheck, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to='eligibility_documents/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'eligibility_documents'
        ordering = ['uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} for {self.eligibility_check}"
