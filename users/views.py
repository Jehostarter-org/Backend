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

from .serializers import (
    RegisterSerializer,
    UserProfileSerializer,
    UserUpdateSerializer,
    EmailTokenObtainPairSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


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
    lookup_field       = 'username'


class GoogleAuthView(APIView):
    permission_classes = [permissions.AllowAny]

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