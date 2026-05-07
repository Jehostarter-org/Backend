from rest_framework import serializers
from .models import MembershipPlan, UserMembership


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MembershipPlan
        fields = '__all__'


class UserMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UserMembership
        fields = ['id', 'plan', 'country_code', 'started_at', 'expires_at', 'is_active']
        read_only_fields = ['id', 'started_at', 'is_active']


class UpgradeMembershipSerializer(serializers.Serializer):
    plan              = serializers.ChoiceField(choices=['silver', 'gold'])
    payment_reference = serializers.CharField()  
