from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView,
    LoginView,
    MeView,
    AvatarUploadView,
    AcceptTermsView,
    ChangePasswordView,
    DeleteAccountView,
    PublicProfileView,
    GoogleAuthView,
)

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('register/',       RegisterView.as_view(),      name='register'),
    path('login/',          LoginView.as_view(),          name='login'),
    path('token/refresh/',  TokenRefreshView.as_view(),   name='token_refresh'),
    path('auth/google/',    GoogleAuthView.as_view(),     name='google_auth'),

    # ── My Account ────────────────────────────────────────────────────────────
    path('me/',              MeView.as_view(),             name='me'),
    path('avatar/',          AvatarUploadView.as_view(),   name='avatar_upload'),
    path('accept-terms/',    AcceptTermsView.as_view(),    name='accept_terms'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('delete-account/',  DeleteAccountView.as_view(),  name='delete_account'),

    # ── Public ────────────────────────────────────────────────────────────────
    path('profile/<str:username>/', PublicProfileView.as_view(), name='public_profile'),
]