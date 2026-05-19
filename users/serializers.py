from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


# ── Auth ──────────────────────────────────────────────────────────────────────

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Allows login with email OR username + password.

    Fixes:
    - MultipleObjectsReturned: use .filter().first() not .get()
    - Case-insensitive email lookup
    - Inactive account check before password validation
    """

    def validate(self, attrs):
        email_or_username = attrs.get('username', '').strip()

        user = None

        # 1. Try email (case-insensitive). Use filter().first() — never .get()
        #    so duplicate rows (from test registrations) don't crash the server.
        if '@' in email_or_username:
            user = (
                User.objects
                .filter(email__iexact=email_or_username, is_active=True)
                .order_by('-date_joined')  # prefer the most recently created
                .first()
            )

        # 2. Fall back to username (case-insensitive)
        if user is None:
            user = (
                User.objects
                .filter(username__iexact=email_or_username, is_active=True)
                .first()
            )

        # 3. Bad credentials — same message for both "not found" and "wrong password"
        #    to avoid leaking which emails are registered.
        if user is None or not user.check_password(attrs.get('password', '')):
            raise serializers.ValidationError(
                {'detail': 'No active account found with the given credentials.'}
            )

        # 4. Swap in the real username so SimpleJWT's parent validate() can
        #    authenticate() the user normally and build the token pair.
        attrs['username'] = user.username
        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        """Embed useful claims directly into the JWT payload."""
        token = super().get_token(user)
        token['email']      = user.email
        token['username']   = user.username
        token['first_name'] = user.first_name
        token['last_name']  = user.last_name
        token['plan']       = user.membership_plan   # from @property on User model
        return token


# ── Registration ──────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'phone',
            'birth_country', 'current_country', 'destination_country',
            'city', 'migration_status',
        ]

    # ── Country validators ────────────────────────────────────────────────────

    def _validate_country(self, value, field_name):
        """Shared validation for all three country fields."""
        if not value:
            return value
        if len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG, AU, GB, US.'
            )
        value = value.upper()
        if value not in settings.SUPPORTED_COUNTRIES:
            raise serializers.ValidationError(
                f'{value} is not supported yet. '
                f'Supported: {", ".join(sorted(settings.SUPPORTED_COUNTRIES))}'
            )
        return value

    def validate_birth_country(self, value):
        if value and len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG, AU, GB.'
            )
        return value.upper() if value else value

    def validate_current_country(self, value):
        return self._validate_country(value, 'current_country')

    def validate_destination_country(self, value):
        return self._validate_country(value, 'destination_country')

    # ── Cross-field validation ────────────────────────────────────────────────

    def validate(self, data):
        if data['password'] != data.pop('password2'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})

        # Prevent duplicate email registrations
        email = data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                {'email': 'An account with this email already exists.'}
            )

        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        # Normalise email to lowercase on save
        validated_data['email'] = validated_data['email'].strip().lower()
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


# ── Profile read ──────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    currency        = serializers.ReadOnlyField()   # from @property
    membership_plan = serializers.ReadOnlyField()   # from @property

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'email',
            'first_name', 'last_name',
            'phone', 'avatar', 'bio', 'is_verified',
            'birth_country', 'current_country', 'destination_country',
            'city', 'state_province', 'migration_status',
            'currency', 'membership_plan',
            'accepted_terms', 'created_at',
        ]
        read_only_fields = [
            'id', 'is_verified', 'currency', 'membership_plan', 'created_at',
        ]


# ── Profile update (PATCH /api/users/me/) ────────────────────────────────────

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = [
            'first_name', 'last_name', 'phone', 'bio',
            'current_country', 'destination_country',
            'city', 'state_province', 'migration_status',
        ]
        # avatar is handled separately by AvatarUploadView (multipart POST)

    def _validate_country(self, value):
        if not value:
            return value
        if len(value) != 2:
            raise serializers.ValidationError(
                'Use a 2-letter country code e.g. NG, AU, GB, US.'
            )
        value = value.upper()
        if value not in settings.SUPPORTED_COUNTRIES:
            raise serializers.ValidationError(
                f'{value} is not a supported country.'
            )
        return value

    def validate_current_country(self, value):
        return self._validate_country(value)

    def validate_destination_country(self, value):
        return self._validate_country(value)