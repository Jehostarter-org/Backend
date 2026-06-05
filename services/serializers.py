from django.core.exceptions import FieldDoesNotExist
from rest_framework import serializers
from .models import (
    ServiceRequest, AirportPickup, HomeInspection, ChaperoneService,
    JobApplicationAssistance, ServiceProviderProfile,
    MigrationSpecialistApplication, ServiceReview,
    Property, PropertyImage,  # ← ADD THESE TWO
)


class AirportPickupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirportPickup
        fields = [
            'id', 'flight_number', 'arrival_datetime', 'airport',
            'terminal', 'pickup_point', 'num_passengers', 'num_bags',
            'special_requests',
        ]


class HomeInspectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeInspection
        fields = [
            'id', 'property_address', 'property_type', 'inspection_date',
            'checklist_items', 'report_notes',
        ]


class ChaperoneServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChaperoneService
        fields = ['id', 'help_type', 'location']


class JobApplicationAssistanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobApplicationAssistance
        fields = [
            'id', 'job_title', 'industry', 'external_job_link',
            'is_remote_service', 'meeting_location',
        ]


class ServiceRequestSerializer(serializers.ModelSerializer):
    airport_pickup_details = AirportPickupSerializer(required=False)
    home_inspection_details = HomeInspectionSerializer(required=False)
    chaperone_details = ChaperoneServiceSerializer(required=False)
    job_application_details = JobApplicationAssistanceSerializer(required=False)

    provider_name = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'requester', 'provider', 'provider_name', 'service_type',
            'description', 'country_code', 'city', 'scheduled_at', 'status',
            'price', 'currency', 'notes', 'created_at', 'updated_at',
            'pickup_address', 'pickup_latitude', 'pickup_longitude',
            'arrival_address', 'arrival_latitude', 'arrival_longitude',
            'distance_km', 'estimated_duration_min',
            'distance_price_multiplier', 'original_base_price',
            'distance_calculation_method',
            'airport_pickup_details', 'home_inspection_details',
            'chaperone_details', 'job_application_details',
        ]
        read_only_fields = [
            'id', 'requester', 'provider', 'created_at', 'updated_at',
            'distance_km', 'estimated_duration_min',
            'distance_price_multiplier', 'original_base_price',
            'distance_calculation_method',
        ]

    def get_provider_name(self, obj):
        if obj.provider and obj.service_type == 'airport_pickup':
            profile = ServiceProviderProfile.objects.filter(
                user=obj.provider,
                service_type='airport_pickup',
            ).first()
            if profile:
                return profile.full_name
            return obj.provider.get_full_name() or obj.provider.username
        if obj.provider:
            return obj.provider.get_full_name() or obj.provider.username
        return None

    def create(self, validated_data):
        airport_data = validated_data.pop('airport_pickup_details', None)
        inspection_data = validated_data.pop('home_inspection_details', None)
        chaperone_data = validated_data.pop('chaperone_details', None)
        job_data = validated_data.pop('job_application_details', None)

        sr = ServiceRequest.objects.create(**validated_data)

        if airport_data:
            AirportPickup.objects.create(service_request=sr, **airport_data)
        if inspection_data:
            HomeInspection.objects.create(service_request=sr, **inspection_data)
        if chaperone_data:
            ChaperoneService.objects.create(service_request=sr, **chaperone_data)
        if job_data:
            JobApplicationAssistance.objects.create(service_request=sr, **job_data)

        return sr


class ServiceReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceReview
        fields = ['id', 'service_request', 'reviewer', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'reviewer', 'created_at']


class ServiceProviderProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = ServiceProviderProfile
        fields = [
            'id', 'user', 'service_type', 'country_code', 'city', 'bio',
            'is_active', 'registered_at',
            'first_name', 'last_name', 'national_identity_number',
            'emergency_contact',
            'license_number', 'license_state_country',
            'license_expiration_date', 'driver_license_image',
            'vehicle_model', 'vehicle_year', 'vehicle_colour',
            'license_plate_number', 'vin',
            'front_view_picture', 'back_view_picture',
            'side_view_picture', 'interior_picture',
            'plate_number_front_view_picture', 'plate_number_back_view_picture',
            'profile_photo',
            'total_trips', 'rating', 'total_reviews',
            'is_available', 'preferred_pickup_location',
            'max_service_distance_km', 'home_base_location',
            'home_base_latitude', 'home_base_longitude',
            'full_name',
        ]
        read_only_fields = [
            'id', 'user', 'registered_at', 'total_trips', 'rating',
            'total_reviews',
        ]

    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.user.get_full_name() or obj.user.username


class MigrationSpecialistApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationSpecialistApplication
        fields = [
            'id', 'user', 'bio', 'qualifications', 'countries_served',
            'languages', 'hourly_rate', 'currency', 'status',
            'rejection_reason', 'reviewed_by', 'reviewed_at',
            'submitted_at',
        ]
        read_only_fields = [
            'id', 'user', 'status', 'rejection_reason',
            'reviewed_by', 'reviewed_at', 'submitted_at',
        ]


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['id', 'image_url', 'order']


class PropertySerializer(serializers.ModelSerializer):
    property_images = PropertyImageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Property
        fields = [
            'id', 'owner', 'property_title', 'property_type', 'rental_type',
            'description', 'address', 'nearest_landmark', 'city', 'state', 'country',
            'bedrooms', 'bathrooms', 'amenities', 'images',
            'available_from', 'price_amount', 'price_type', 'security_deposit',
            'min_stay_duration', 'max_stay_duration', 'house_rules',
            'status', 'is_published', 'created_at', 'updated_at', 'property_images'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']


_CAMEL_TO_SNAKE = {
    'propertyTitle':  'property_title',
    'propertyType':   'property_type',
    'rentalType':     'rental_type',
    'nearestLandmark': 'nearest_landmark',
    'availableFrom':  'available_from',
    'priceAmount':    'price_amount',
    'priceType':      'price_type',
    'securityDeposit': 'security_deposit',
    'minStayDuration': 'min_stay_duration',
    'maxStayDuration': 'max_stay_duration',
    'houseRules':     'house_rules',
    'isPublished':    'is_published',
}


class PropertyCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = '__all__'
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at', 'status']
        extra_kwargs = {
            'price_amount': {'required': False, 'default': 0},
            'price_type':   {'required': False, 'default': 'monthly'},
            'bedrooms':     {'required': False, 'default': 1},
            'bathrooms':    {'required': False, 'default': 1},
            'country':      {'required': False, 'default': 'NG'},
            'amenities':    {'required': False, 'default': list},
            'images':       {'required': False, 'default': list},
            'house_rules':  {'required': False, 'default': list},
            'min_stay_duration': {'required': False, 'default': 1},
        }

    def to_internal_value(self, data):
        # Translate camelCase keys from the frontend to snake_case for the model
        if isinstance(data, dict):
            translated = {}
            for key, value in data.items():
                translated[_CAMEL_TO_SNAKE.get(key, key)] = value
            data = translated

        # Convert empty strings to None for nullable model fields so DRF
        # IntegerField / DateField / CharField(blank=True) don't choke on "".
        for field_name in data:
            try:
                model_field = self.Meta.model._meta.get_field(field_name)
            except FieldDoesNotExist:
                continue
            if data[field_name] == '' and model_field.null:
                data[field_name] = None

        return super().to_internal_value(data)