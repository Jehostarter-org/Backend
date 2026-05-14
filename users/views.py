from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.utils import timezone

from .serializers import (
    RegisterSerializer,
    UserProfileSerializer,
    UserUpdateSerializer,
    EmailTokenObtainPairSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """
    POST /api/users/register/
    Open to anyone. Creates a new user account.
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    """
    POST /api/users/login/
    Accepts email OR username + password.
    Returns { access, refresh } JWT tokens.
    """
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/users/me/  — returns full profile of logged-in user
    PATCH /api/users/me/  — partial update
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserProfileSerializer


class AvatarUploadView(APIView):
    """
    POST /api/users/avatar/
    File upload stays in DRF — easier than GraphQL for multipart.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
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
    """
    POST /api/users/accept-terms/
    Records terms acceptance. Called during onboarding.
    """
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
    """
    POST /api/users/change-password/
    Requires current password before setting a new one.
    """
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
    """
    POST /api/users/delete-account/
    Soft deletes — deactivates rather than hard deletes.
    """
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
    """
    GET /api/users/profile/<username>/
    Public — no auth required.
    """
    queryset         = User.objects.filter(is_active=True)
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field     = 'username'



"""
Add this to your users/views.py

Also add to requirements.txt:
  google-auth
  google-auth-oauthlib

And add to your .env:
  GOOGLE_CLIENT_ID=282926972818-cgcmau1p3f7o20giscv70f6mvle09n5f.apps.googleusercontent.com
  GOOGLE_CLIENT_SECRET=your-regenerated-secret-here
"""

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken
from decouple import config


class GoogleAuthView(APIView):
    """
    POST /api/users/auth/google/

    Receives the Google ID token from the frontend.
    Verifies it with Google, creates or retrieves the user,
    and returns Django JWT tokens.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        credential = request.data.get('credential')

        if not credential:
            return Response(
                {'error': 'Google credential is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Verify the token with Google
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
        picture    = id_info.get('picture', '')

        if not email:
            return Response(
                {'error': 'Could not retrieve email from Google.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get or create the user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username':   email.split('@')[0],
                'first_name': first_name,
                'last_name':  last_name,
                'is_verified': True,  # Google accounts are pre-verified
            }
        )

        # Update name/picture if user already exists
        if not created:
            if not user.first_name:
                user.first_name = first_name
            if not user.last_name:
                user.last_name = last_name
            user.save(update_fields=['first_name', 'last_name'])

        # Generate Django JWT tokens for this user
        refresh = RefreshToken.for_user(user)

        return Response({
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'created': created,  # True if new user, False if existing
        }, status=status.HTTP_200_OK)