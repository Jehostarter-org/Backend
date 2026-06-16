from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.utils import timezone
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from decouple import config
from django.contrib.gis.geos import Point
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


from .serializers import (
    RegisterSerializer,
    RegisterResponseSerializer,
    VerifyEmailSerializer,
    UserProfileSerializer,
    UserUpdateSerializer,
    EmailTokenObtainPairSerializer,
    AdminRegisterSerializer,
    AdminTokenObtainPairSerializer,
    AdminProfileSerializer,
)
from .email_verification import send_verification_email, verify_code

User = get_user_model()


class IsStaffUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        try:
            send_verification_email(user)
        except Exception as exc:
            return Response(
                {
                    'detail': 'Account created but we could not send the verification email. '
                              'Use resend on the verify page or check email settings.',
                    'email_error': str(exc),
                    'id': user.id,
                    'email': user.email,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        data = RegisterResponseSerializer(user).data
        return Response(data, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if user.is_verified:
            return Response({'detail': 'Email is already verified.', 'is_verified': True})
        ok, message = verify_code(user, serializer.validated_data['code'])
        if not ok:
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': message, 'is_verified': True})


class ResendVerificationEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.is_verified:
            return Response({'detail': 'Email is already verified.'})
        try:
            send_verification_email(user)
        except Exception as exc:
            return Response(
                {'detail': f'Could not send email: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'detail': 'Verification code sent. Check your inbox.'})


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []


class AdminRegisterView(generics.CreateAPIView):
    queryset           = User.objects.all()
    serializer_class   = AdminRegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []


class AdminLoginView(TokenObtainPairView):
    serializer_class   = AdminTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []


class AdminMeView(generics.RetrieveAPIView):
    permission_classes = [IsStaffUser]
    serializer_class   = AdminProfileSerializer

    def get_object(self):
        return self.request.user


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserProfileSerializer


class AvatarUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user   = request.user
        avatar = request.FILES.get('avatar')

        if not avatar:
            return Response(
                {'error': 'No image provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.avatar:
            user.avatar.delete(save=False)

        user.avatar = avatar
        user.save(update_fields=['avatar'])

        return Response(
            {'avatar': request.build_absolute_uri(user.avatar.url)},
            status=status.HTTP_200_OK,
        )


class AcceptTermsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.accepted_terms:
            return Response(
                {'detail': 'Terms already accepted.'},
                status=status.HTTP_200_OK,
            )

        user.accepted_terms    = True
        user.accepted_terms_at = timezone.now()
        user.save(update_fields=['accepted_terms', 'accepted_terms_at'])

        return Response(
            {'detail': 'Terms accepted successfully.'},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user          = request.user
        current       = request.data.get('current_password')
        new_password  = request.data.get('new_password')
        new_password2 = request.data.get('new_password2')

        if not current or not new_password or not new_password2:
            return Response(
                {'error': 'All fields are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(current):
            return Response(
                {'error': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != new_password2:
            return Response(
                {'error': 'New passwords do not match.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'error': 'Password must be at least 8 characters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response(
            {'detail': 'Password changed successfully. Please log in again.'},
            status=status.HTTP_200_OK,
        )


class DeleteAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user     = request.user
        password = request.data.get('password')

        if not password:
            return Response(
                {'error': 'Password is required to delete your account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(password):
            return Response(
                {'error': 'Incorrect password.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False
        user.save(update_fields=['is_active'])

        return Response(
            {'detail': 'Account deactivated successfully.'},
            status=status.HTTP_200_OK,
        )


class PublicProfileView(generics.RetrieveAPIView):
    queryset           = User.objects.filter(is_active=True)
    serializer_class   = UserProfileSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    lookup_field       = 'username'


class GoogleAuthView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        credential = request.data.get('credential')

        if not credential:
            return Response(
                {'error': 'Google credential is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            google_client_id = config('GOOGLE_CLIENT_ID')
            id_info = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                google_client_id,
            )
        except ValueError as e:
            return Response(
                {'error': f'Invalid Google token: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email      = id_info.get('email')
        first_name = id_info.get('given_name', '')
        last_name  = id_info.get('family_name', '')

        if not email:
            return Response(
                {'error': 'Could not retrieve email from Google.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Safe lookup — handles duplicate accounts from earlier testing
        try:
            user = User.objects.get(email=email)
            created = False
        except User.MultipleObjectsReturned:
            # Keep the most recently created account, delete the rest
            users = User.objects.filter(email=email).order_by('-created_at')
            user = users.first()
            users.exclude(id=user.id).delete()
            created = False
        except User.DoesNotExist:
            # Generate a unique username if the email prefix is already taken
            base_username = email.split('@')[0]
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f'{base_username}{counter}'
                counter += 1

            user = User.objects.create(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_verified=True,
            )
            created = True

        # Update name if missing
        if not created:
            updated = False
            if not user.first_name and first_name:
                user.first_name = first_name
                updated = True
            if not user.last_name and last_name:
                user.last_name = last_name
                updated = True
            if updated:
                user.save(update_fields=['first_name', 'last_name'])

        refresh = RefreshToken.for_user(user)

        return Response({
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'created': created,
        }, status=status.HTTP_200_OK)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_location(request):
    lat = request.data.get('latitude')
    lng = request.data.get('longitude')
    source = request.data.get('source', 'gps')

    if lat is None or lng is None:
        return Response({'error': 'latitude and longitude required'}, status=400)

    try:
        request.user.location = Point(float(lng), float(lat), srid=4326)
        request.user.location_source = source
        request.user.save(update_fields=['location', 'location_source'])
        return Response({'status': 'location updated'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)


class AdminUserListView(generics.ListAPIView):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserProfileSerializer
    permission_classes = [IsStaffUser]


class AdminUserDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsStaffUser]

# ── Forgot / Reset Password ───────────────────────────────────────────────────

from .serializers import ForgotPasswordSerializer, ResetPasswordSerializer
from .password_reset import send_password_reset_email, verify_reset_token, mark_token_used


class ForgotPasswordView(APIView):
    """
    POST /api/users/forgot-password/

    Accepts an email. If the email is registered, sends a reset link.
    Always returns 200 to prevent email enumeration.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        # Always return success — never reveal whether the email exists.
        user = (
            User.objects
            .filter(email__iexact=email, is_active=True)
            .first()
        )

        if user is not None:
            try:
                send_password_reset_email(user)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(
                    'Failed to send password reset email to %s: %s', email, exc,
                )
                # Still return 200 — we don't want to leak info.

        return Response(
            {
                'detail': (
                    'If an account exists with that email address, '
                    'you will receive a password reset link shortly.'
                ),
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    """
    POST /api/users/reset-password/

    Accepts a token + new_password. Verifies the token,
    hashes the new password with Argon2 (Django default),
    and marks the token as used.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        user, error = verify_reset_token(token)
        if error:
            return Response(
                {'detail': error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # set_password uses Django's PASSWORD_HASHERS — Argon2 is first.
        user.set_password(new_password)
        user.save(update_fields=['password'])

        # Mark the token as used
        mark_token_used(token)

        return Response(
            {'detail': 'Password has been reset successfully. You can now log in.'},
            status=status.HTTP_200_OK,
        )
