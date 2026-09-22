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
        ('chaperone',            'Chaperone Services'),
        ('temporary_housing',    'Temporary Housing'),
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

    # ── Distance Tracking for Airport Pickup ──────────────────────────────────
    # Pickup location (where the rider is being picked up from)
    pickup_address = models.TextField(blank=True, null=True, help_text="Pickup address (home/hotel/office)")
    pickup_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # Arrival location (airport)
    arrival_address = models.TextField(blank=True, null=True, help_text="Airport address")
    arrival_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    arrival_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # Calculated distance and duration
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Distance from pickup to airport in kilometers")
    estimated_duration_min = models.IntegerField(null=True, blank=True, help_text="Estimated driving duration in minutes")
    
    # Dynamic pricing based on distance
    distance_price_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, help_text="Multiplier applied to base price based on distance")
    original_base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Original base price before distance multiplier")
    
    # Distance calculation method used
    distance_calculation_method = models.CharField(max_length=20, blank=True, choices=[
        ('routing', 'Routing API (OSRM/GraphHopper)'),
        ('straight_line', 'Straight Line (Haversine)'),
        ('manual', 'Manually Entered'),
    ], help_text="Method used to calculate distance")

    passenger_rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Driver's rating of the passenger (1-5)")
    passenger_review_comment = models.TextField(blank=True, help_text="Driver's review comment about the passenger")

    class Meta:
        db_table = 'service_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_service_type_display()} – {self.requester}"
    
    @property
    def total_price(self):
        """Return the final price including distance multiplier"""
        if self.price and self.distance_price_multiplier:
            return self.price * self.distance_price_multiplier
        return self.price
    
    @property
    def has_distance_calculated(self):
        """Check if distance has been calculated"""
        return self.distance_km is not None and self.distance_km > 0


class AirportPickup(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    service_request  = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='airport_pickup_details')
    flight_number    = models.CharField(max_length=20, default='', blank=True)
    arrival_datetime = models.DateTimeField(null=True, blank=True)   # FIX: nullable so create() can validate first
    airport          = models.CharField(max_length=200)
    terminal         = models.CharField(max_length=50, blank=True)
    pickup_point     = models.CharField(max_length=100, blank=True)  # FIX: proper field (was being crammed into special_requests)
    num_passengers   = models.PositiveIntegerField(default=1)
    num_bags         = models.PositiveIntegerField(default=1)
    special_requests = models.TextField(blank=True)
    driver           = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pickup_jobs'
    )
    
    # ── Airport Specific Distance Fields ──────────────────────────────────────
    # Distance from pickup point to the specific terminal
    distance_to_terminal_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, 
                                                   help_text="Distance from pickup address to airport terminal")
    waiting_time_min = models.IntegerField(null=True, blank=True, 
                                          help_text="Estimated waiting time at airport")
    
    # Alternative pickup points at the airport (for driver to know)
    suggested_pickup_spot = models.CharField(max_length=200, blank=True, 
                                            help_text="Suggested meeting point at the airport (e.g., 'Departures Gate B')")
    
    # Flight tracking
    flight_status = models.CharField(max_length=20, blank=True, choices=[
        ('on_time', 'On Time'),
        ('delayed', 'Delayed'),
        ('cancelled', 'Cancelled'),
        ('landed', 'Landed'),
    ], help_text="Current flight status")
    
    actual_landing_time = models.DateTimeField(null=True, blank=True, help_text="Actual landing time of the flight")
    driver_arrived_at = models.DateTimeField(null=True, blank=True, help_text="When driver arrived at airport")
    passenger_picked_up_at = models.DateTimeField(null=True, blank=True, help_text="When passenger was actually picked up")

    class Meta:
        db_table = 'airport_pickups'

    def __str__(self):
        return f"Pickup – {self.flight_number} @ {self.airport}"
    
    @property
    def is_flight_landed(self):
        """Check if flight has landed"""
        if self.actual_landing_time:
            from django.utils import timezone
            return self.actual_landing_time <= timezone.now()
        return False
    
    @property
    def waiting_time_actual_min(self):
        """Calculate actual waiting time from driver arrival to passenger pickup"""
        if self.driver_arrived_at and self.passenger_picked_up_at:
            delta = self.passenger_picked_up_at - self.driver_arrived_at
            return int(delta.total_seconds() / 60)
        return None


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
    
    # Distance tracking for home inspection
    distance_from_inspector_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                                      help_text="Distance from inspector's location to property")
    inspection_duration_min = models.IntegerField(null=True, blank=True, default=60,
                                                  help_text="Estimated inspection duration in minutes")

    class Meta:
        db_table = 'home_inspections'

    def __str__(self):
        return f"Inspection – {self.property_address}"


class ChaperoneService(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    HELP_TYPES = [
        ('arrival',            'Arrival'),
        ('housing',            'Housing'),
        ('administration',     'Administration'),
        ('employment',         'Employment'),
        ('settlement',         'Settlement'),
        ('appointments',       'Appointments'),
        ('transport',          'Transport'),
        ('education',          'Education'),
        ('digital',            'Digital'),
        ('shopping',           'Shopping'),
        ('communication',      'Communication'),
        ('community',          'Community'),
        ('local_orientation',  'Local Orientation'),
        ('moving',             'Moving'),
        ('family_settlement',  'Family Settlement'),
        ('business_setup',     'Business Setup'),
        ('general_errands',    'General Errands'),
    ]

    service_request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='chaperone_details')
    help_type       = models.JSONField(default=list, blank=True)
    location        = models.CharField(max_length=200, blank=True)
    address         = models.TextField(blank=True, null=True, help_text="Full street address where assistance is needed")
    chaperone       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chaperone_jobs'
    )
    
    # Distance tracking for chaperone
    distance_to_location_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                                   help_text="Distance from chaperone to service location")
    estimated_service_time_min = models.IntegerField(null=True, blank=True, default=30,
                                                     help_text="Estimated time to complete service in minutes")

    class Meta:
        db_table = 'chaperone_services'


class TemporaryHousing(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    service_request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='temporary_housing_details')
    property_address = models.TextField()
    check_in_date    = models.DateField()
    check_out_date   = models.DateField()
    num_guests       = models.PositiveIntegerField(default=1)
    num_rooms        = models.PositiveIntegerField(default=1)
    special_requests = models.TextField(blank=True)
    host             = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='temporary_housing_hosted'
    )

    class Meta:
        db_table = 'temporary_housing'

    def __str__(self):
        return f"Temporary Housing – {self.property_address}"


class ServiceProviderProfile(models.Model):
    """
    A user registers for one or more service types they want to offer.
    Each registration is a separate row — one profile per service type per user.
    Location is city-level: a Lagos driver only sees Lagos pickups.

    For drivers (airport_pickup service type), this stores all their personal,
    license, and vehicle information including photos that riders will see.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    SERVICE_TYPES = [
        ('airport_pickup',   'Driver'),
        ('home_inspection',  'Home Inspector'),
        ('chaperone',        'Chaperone'),
        ('temporary_housing','Temporary Housing Host'),
    ]
    # Note: migration_specialist is excluded here — it has its own application flow

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='provider_profiles')
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPES)
    country_code = models.CharField(max_length=2)
    city         = models.CharField(max_length=100)  # strict city-level matching
    bio          = models.TextField(blank=True, help_text="Brief introduction about yourself")
    is_active    = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    # ── Approval Workflow ────────────────────────────────────────────────────
    APPROVAL_STATUS = [
        ('pending',  'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    approval_status  = models.CharField(max_length=10, choices=APPROVAL_STATUS, default='pending')
    rejection_reason = models.TextField(blank=True, help_text="Reason for rejection (if rejected)")
    reviewed_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_provider_profiles'
    )
    reviewed_at      = models.DateTimeField(null=True, blank=True)

    # ── Personal Information ──────────────────────────────────────────────────
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    national_identity_number = models.CharField(max_length=50, blank=True, help_text="National ID / NIN")
    emergency_contact = models.CharField(max_length=20, blank=True, help_text="Emergency phone number")

    # ── Driver License Information ────────────────────────────────────────────
    license_number = models.CharField(max_length=50, blank=True)
    license_state_country = models.CharField(max_length=100, blank=True, help_text="State/Country that issued the license")
    license_expiration_date = models.DateField(null=True, blank=True)
    driver_license_image = models.ImageField(
        upload_to='driver_licenses/',
        null=True, blank=True,
        help_text="Upload a clear photo of your driver's license"
    )

    # ── Vehicle Information ───────────────────────────────────────────────────
    vehicle_model = models.CharField(max_length=100, blank=True, help_text="e.g., Toyota Camry")
    vehicle_year = models.CharField(max_length=4, blank=True, help_text="e.g., 2020")
    vehicle_colour = models.CharField(max_length=30, blank=True, help_text="e.g., Red, Blue, Black")
    license_plate_number = models.CharField(max_length=20, blank=True, help_text="Vehicle license plate number")
    vin = models.CharField(max_length=50, blank=True, help_text="Vehicle Identification Number (Optional)")

    # ── Vehicle Photos (For riders to identify the car) ───────────────────────
    front_view_picture = models.ImageField(
        upload_to='vehicle_photos/front/',
        null=True, blank=True,
        help_text="Front view of your vehicle - riders will see this"
    )
    back_view_picture = models.ImageField(
        upload_to='vehicle_photos/back/',
        null=True, blank=True,
        help_text="Back view of your vehicle"
    )
    side_view_picture = models.ImageField(
        upload_to='vehicle_photos/side/',
        null=True, blank=True,
        help_text="Side view of your vehicle"
    )
    interior_picture = models.ImageField(
        upload_to='vehicle_photos/interior/',
        null=True, blank=True,
        help_text="Interior view of your vehicle"
    )

    # ── License Plate Photos ──────────────────────────────────────────────────
    plate_number_front_view_picture = models.ImageField(
        upload_to='plate_photos/front/',
        null=True, blank=True,
        help_text="Clear photo of front license plate"
    )
    plate_number_back_view_picture = models.ImageField(
        upload_to='plate_photos/back/',
        null=True, blank=True,
        help_text="Clear photo of back license plate"
    )

    # ── Chaperone-specific Fields ────────────────────────────────────────────
    sim_card_reference = models.CharField(max_length=50, blank=True, help_text="SIM card registration reference number")
    phone_number = models.CharField(max_length=20, blank=True, help_text="Contact phone number of the chaperone")
    tax_file_number_reference = models.CharField(max_length=50, blank=True, help_text="Tax File Number (TFN) reference")
    offers_translation_service = models.BooleanField(default=False, help_text="Can provide translation services")
    offers_registration_service = models.BooleanField(default=False, help_text="Can help with all forms of registration")
    is_immigration_officer = models.BooleanField(default=False, help_text="Currently or previously worked as an immigration officer")

    # ── Driver Profile Photo ──────────────────────────────────────────────────
    profile_photo = models.ImageField(
        upload_to='driver_photos/',
        null=True, blank=True,
        help_text="Your profile photo - riders will see this"
    )

    # ── Driver Statistics ─────────────────────────────────────────────────────
    total_trips = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)

    # ── Availability ──────────────────────────────────────────────────────────
    is_available = models.BooleanField(default=True, help_text="Are you currently available for pickups?")
    preferred_pickup_location = models.CharField(max_length=200, blank=True, help_text="Your preferred airport pickup location")
    
    # ── Driver Service Radius ─────────────────────────────────────────────────
    max_service_distance_km = models.PositiveIntegerField(default=50, help_text="Maximum distance in km you're willing to drive for pickups")
    home_base_location = models.CharField(max_length=200, blank=True, help_text="Your home base location for calculating distances")
    home_base_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    home_base_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    class Meta:
        db_table = 'service_provider_profiles'
        unique_together = ('user', 'service_type')

    def __str__(self):
        return f"{self.user} – {self.get_service_type_display()} in {self.city}"

    @property
    def full_name(self):
        """Return the driver's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.user.get_full_name() or self.user.username

    @property
    def vehicle_display(self):
        """Return a formatted string of vehicle details for riders"""
        return f"{self.vehicle_colour} {self.vehicle_model} ({self.vehicle_year})"

    @property
    def has_complete_profile(self):
        """Check if the driver has completed all required information"""
        required_fields = [
            self.first_name, self.last_name, self.national_identity_number,
            self.license_number, self.license_plate_number,
            self.vehicle_model, self.vehicle_year, self.vehicle_colour,
            self.driver_license_image, self.front_view_picture
        ]
        return all(required_fields)
    
    @property
    def average_response_time_min(self):
        """Calculate average response time for this driver"""
        # This would need to be implemented with actual tracking data
        # For now, return a default or calculate from service history
        return 15  # Default 15 minutes


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


# ── Distance Tracking Log (Optional: For analytics and debugging) ─────────────

class DistanceCalculationLog(models.Model):
    """
    Log all distance calculations for debugging and analytics
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='distance_logs')
    calculation_method = models.CharField(max_length=20, choices=[
        ('routing', 'Routing API'),
        ('straight_line', 'Straight Line'),
        ('manual', 'Manual Entry'),
    ])
    
    pickup_coords = models.CharField(max_length=100, blank=True, help_text="lat,lon")
    arrival_coords = models.CharField(max_length=100, blank=True, help_text="lat,lon")
    
    calculated_distance_km = models.DecimalField(max_digits=10, decimal_places=2)
    calculated_duration_min = models.IntegerField(null=True, blank=True)
    
    api_response_time_ms = models.IntegerField(null=True, blank=True, help_text="API response time in milliseconds")
    api_status_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'distance_calculation_logs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Distance log for {self.service_request.id} - {self.calculated_distance_km}km"

class Property(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    
    # Owner
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='properties')
    
    # Step 1: Basic Info
    property_title = models.CharField(max_length=200)
    property_type = models.CharField(max_length=50)  # apartment, house, condo, etc.
    rental_type = models.CharField(max_length=20)  # short-term, long-term
    description = models.TextField()
    address = models.TextField()
    nearest_landmark = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=2, default='NG')
    
    # Step 2: Features
    bedrooms = models.IntegerField(default=1)
    bathrooms = models.DecimalField(max_digits=3, decimal_places=1, default=1)
    amenities = models.JSONField(default=list)  # List of amenity IDs
    images = models.JSONField(default=list)  # List of image URLs
    
    # Step 3: Availability & Pricing
    available_from = models.DateField(null=True, blank=True)
    price_amount = models.DecimalField(max_digits=12, decimal_places=2)
    price_type = models.CharField(max_length=10, default='monthly')  # daily, weekly, monthly, yearly
    security_deposit = models.BooleanField(default=False)
    min_stay_duration = models.IntegerField(default=1)  # in days
    max_stay_duration = models.IntegerField(null=True, blank=True)
    house_rules = models.JSONField(default=list)  # List of rule IDs
    
    # Status
    status = models.CharField(max_length=20, default='draft')  # draft, published, rented, unavailable
    is_published = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'properties'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.property_title

class PropertyImage(models.Model):
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='property_images')
    image_url = models.URLField()
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'property_images'
        ordering = ['order']