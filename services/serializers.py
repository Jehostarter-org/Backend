from rest_framework import serializers
from django.conf import settings
from .models import ServiceRequest, AirportPickup, HomeInspection, ChaperoneService, ServiceReview


class AirportPickupSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AirportPickup
        fields = ['flight_number', 'arrival_datetime', 'airport', 'terminal', 'num_passengers', 'num_bags', 'special_requests']


class HomeInspectionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HomeInspection
        fields = ['property_address', 'property_type', 'inspection_date', 'checklist_items', 'report', 'report_notes']
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
    airport_pickup_details   = AirportPickupSerializer(required=False)
    home_inspection_details  = HomeInspectionSerializer(required=False)
    chaperone_details        = ChaperoneSerializer(required=False)
    review                   = ServiceReviewSerializer(read_only=True)
    requester_name           = serializers.ReadOnlyField(source='requester.get_full_name')

    class Meta:
        model  = ServiceRequest
        fields = [
            'id', 'requester', 'requester_name', 'provider', 'service_type',
            'description', 'country_code', 'city', 'scheduled_at',
            'status', 'price', 'currency', 'notes', 'created_at',
            'airport_pickup_details', 'home_inspection_details', 'chaperone_details', 'review',
        ]
        read_only_fields = ['id', 'requester', 'status', 'created_at']

    def create(self, validated_data):
        airport_data   = validated_data.pop('airport_pickup_details', None)
        inspection_data = validated_data.pop('home_inspection_details', None)
        chaperone_data  = validated_data.pop('chaperone_details', None)
        user     = self.context['request'].user
        currency = settings.COUNTRY_CURRENCY_MAP.get(user.current_country, 'USD')
        sr = ServiceRequest.objects.create(
            requester=user, currency=currency,
            country_code=user.current_country, **validated_data
        )
        if airport_data:
            AirportPickup.objects.create(service_request=sr, **airport_data)
        if inspection_data:
            HomeInspection.objects.create(service_request=sr, **inspection_data)
        if chaperone_data:
            ChaperoneService.objects.create(service_request=sr, **chaperone_data)
        return sr  
