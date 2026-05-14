from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.conf import settings
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Override SimpleJWT to accept email instead of username.
    The frontend sends { username: email, password } and we
    look up the user by email before authenticating.
    """
    def validate(self, attrs):
        # SimpleJWT uses 'username' as the field name by default
        # We intercept it and treat it as an email
        email_or_username = attrs.get('username', '')

        # Try to find the user by email first, then by username
        user = None
        try:
            user = User.objects.get(email=email_or_username)
            # Replace the email with the actual username for authentication
            attrs['username'] = user.username
        except User.DoesNotExist:
            # Fall through — let SimpleJWT handle it normally
            pass

        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims to the JWT payload
        token['email']      = user.email
        token['username']   = user.username
        token['first_name'] = user.first_name
        token['last_name']  = user.last_name
        return token


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'phone',
            'birth_country', 'current_country', 'destination_country',
            'city', 'migration_status',
        ]

    def validate_birth_country(self, value):
        if value and len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG for Nigeria, AU for Australia, GB for UK.'
            )
        return value.upper() if value else value

    def validate_current_country(self, value):
        if not value:
            return value
        if len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG for Nigeria, AU for Australia, GB for UK.'
            )
        value = value.upper()
        if value not in settings.SUPPORTED_COUNTRIES:
            raise serializers.ValidationError(
                f'{value} is not supported yet. Supported countries: {", ".join(settings.SUPPORTED_COUNTRIES)}'
            )
        return value

    def validate_destination_country(self, value):
        if not value:
            return value
        if len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG for Nigeria, AU for Australia, GB for UK.'
            )
        value = value.upper()
        if value not in settings.SUPPORTED_COUNTRIES:
            raise serializers.ValidationError(
                f'{value} is not supported yet. Supported countries: {", ".join(settings.SUPPORTED_COUNTRIES)}'
            )
        return value

    def validate(self, data):
        if data['password'] != data.pop('password2'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    currency        = serializers.ReadOnlyField()
    membership_plan = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone', 'avatar', 'bio', 'is_verified',
            'birth_country', 'current_country', 'destination_country',
            'city', 'state_province', 'migration_status',
            'currency', 'membership_plan', 'created_at',
            'accepted_terms',
        ]
        read_only_fields = [
            'id', 'is_verified', 'currency', 'membership_plan', 'created_at'
        ]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone', 'avatar', 'bio',
            'current_country', 'destination_country', 'city',
            'state_province', 'migration_status',
        ]

    def validate_current_country(self, value):
        if not value:
            return value
        if len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG for Nigeria, AU for Australia.'
            )
        value = value.upper()
        if value not in settings.SUPPORTED_COUNTRIES:
            raise serializers.ValidationError(
                f'{value} is not a supported country.'
            )
        return value

    def validate_destination_country(self, value):
        if not value:
            return value
        if len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG for Nigeria, AU for Australia.'
            )
        value = value.upper()
        if value not in settings.SUPPORTED_COUNTRIES:
            raise serializers.ValidationError(
                f'{value} is not a supported country.'
            )
        return value