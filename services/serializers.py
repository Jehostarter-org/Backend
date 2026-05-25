from rest_framework import serializers
from django.conf import settings
from .models import (
    ServiceRequest, AirportPickup, HomeInspection,
    ChaperoneService, ServiceReview,
    ServiceProviderProfile, MigrationSpecialistApplication,
)


class AirportPickupSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AirportPickup
        fields = [
            'flight_number', 'arrival_datetime', 'airport',
            'terminal', 'num_passengers', 'num_bags', 'special_requests',
        ]


class HomeInspectionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HomeInspection
        fields = [
            'property_address', 'property_type', 'inspection_date',
            'checklist_items', 'report', 'report_notes',
        ]
        read_only_fields = ['report']


class ChaperoneSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ChaperoneService
        fields = ['help_type', 'location']


class ServiceReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ServiceReview
        fields = ['id', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value


class ServiceRequestSerializer(serializers.ModelSerializer):
    airport_pickup_details  = AirportPickupSerializer(required=False)
    home_inspection_details = HomeInspectionSerializer(required=False)
    chaperone_details       = ChaperoneSerializer(required=False)
    review                  = ServiceReviewSerializer(read_only=True)
    requester_name          = serializers.ReadOnlyField(source='requester.get_full_name')
    provider_name           = serializers.ReadOnlyField(source='provider.get_full_name')

    class Meta:
        model  = ServiceRequest
        fields = [
            'id', 'requester', 'requester_name', 'provider', 'provider_name',
            'service_type', 'description', 'country_code', 'city',
            'scheduled_at', 'status', 'price', 'currency', 'notes',
            'created_at', 'updated_at',
            'airport_pickup_details', 'home_inspection_details',
            'chaperone_details', 'review',
        ]
        read_only_fields = [
            'id', 'requester', 'provider', 'status', 'country_code', 'city',
            'currency', 'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        airport_data    = validated_data.pop('airport_pickup_details', None)
        inspection_data = validated_data.pop('home_inspection_details', None)
        chaperone_data  = validated_data.pop('chaperone_details', None)

        user     = self.context['request'].user
        currency = settings.COUNTRY_CURRENCY_MAP.get(user.current_country, 'USD')

        sr = ServiceRequest.objects.create(
            requester=user,
            currency=currency,
            country_code=user.current_country,
            city=user.city,
            **validated_data,
        )

        if airport_data:
            AirportPickup.objects.create(service_request=sr, **airport_data)
        if inspection_data:
            HomeInspection.objects.create(service_request=sr, **inspection_data)
        if chaperone_data:
            ChaperoneService.objects.create(service_request=sr, **chaperone_data)

        return sr


class ServiceProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ServiceProviderProfile
        fields = [
            'id', 'service_type', 'country_code', 'city', 'bio', 'is_active', 'registered_at',
        ]
        read_only_fields = ['id', 'registered_at']

    def validate_service_type(self, value):
        valid = ['airport_pickup', 'home_inspection', 'chaperon', 'job_application']
        if value not in valid:
            raise serializers.ValidationError(
                f'Invalid service type. Choose from: {", ".join(valid)}'
            )
        return value

    def validate(self, data):
        user = self.context['request'].user
        service_type = data.get('service_type')
        # Prevent duplicate registrations for the same service type
        if ServiceProviderProfile.objects.filter(user=user, service_type=service_type).exists():
            raise serializers.ValidationError(
                f'You are already registered as a {service_type} provider.'
            )
        return data

    def create(self, validated_data):
        return ServiceProviderProfile.objects.create(
            user=self.context['request'].user,
            **validated_data,
        )


class MigrationSpecialistApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MigrationSpecialistApplication
        fields = [
            'id', 'bio', 'qualifications', 'countries_served',
            'languages', 'hourly_rate', 'currency',
            'status', 'rejection_reason', 'submitted_at',
        ]
        read_only_fields = ['id', 'status', 'rejection_reason', 'submitted_at']

    def validate(self, data):
        user = self.context['request'].user
        if MigrationSpecialistApplication.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                'You have already submitted an application. '
                'Please wait for admin review.'
            )
        return data

    def create(self, validated_data):
        return MigrationSpecialistApplication.objects.create(
            user=self.context['request'].user,
            **validated_data,
        )
