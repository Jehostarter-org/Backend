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
    Returns access + refresh JWT tokens.
    """
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/users/me/  — returns full profile of logged-in user
    PUT  /api/users/me/  — full update
    PATCH /api/users/me/ — partial update (recommended)
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
    Handles avatar image upload separately from other profile fields.
    Stays in DRF because file uploads are easier here than in GraphQL.
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

        # Delete old avatar to save storage
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
    Records that the user has accepted the terms and conditions.
    Called during onboarding — only works once.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.accepted_terms:
            return Response(
                {'detail': 'Terms already accepted.'},
                status=status.HTTP_200_OK,
            )

        user.accepted_terms = True
        user.accepted_terms_at = timezone.now()
        user.save(update_fields=['accepted_terms', 'accepted_terms_at'])

        return Response(
            {'detail': 'Terms accepted successfully.'},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """
    POST /api/users/change-password/
    Requires the current password before setting a new one.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        new_password2 = request.data.get('new_password2')

        if not current_password or not new_password or not new_password2:
            return Response(
                {'error': 'All fields are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(current_password):
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
    Requires password confirmation before deleting.
    Soft approach: deactivates the account rather than hard deleting,
    so related data (posts, orders, reviews) stays intact.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
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

        # Deactivate instead of hard delete — preserves data integrity
        user.is_active = False
        user.save(update_fields=['is_active'])

        return Response(
            {'detail': 'Account deactivated successfully.'},
            status=status.HTTP_200_OK,
        )


class PublicProfileView(generics.RetrieveAPIView):
    """
    GET /api/users/profile/<username>/
    Anyone can view a public profile — no auth required.
    """
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'username'