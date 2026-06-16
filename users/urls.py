from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView, LoginView, MeView, AvatarUploadView,
    AcceptTermsView, ChangePasswordView, DeleteAccountView,
    PublicProfileView, GoogleAuthView,
    AdminRegisterView, AdminLoginView, AdminMeView,
    AdminUserListView, AdminUserDetailView, ForgotPasswordView, ResetPasswordView,
)
from .location_view import UpdateLocationView, DetectLocationView

urlpatterns = [
    path('register/',       RegisterView.as_view(),      name='register'),
    path('login/',          LoginView.as_view(),          name='login'),
    path('admin/register/', AdminRegisterView.as_view(),  name='admin_register'),
    path('admin/login/',    AdminLoginView.as_view(),     name='admin_login'),
    path('admin/me/',       AdminMeView.as_view(),        name='admin_me'),
    path('admin/users/',    AdminUserListView.as_view(),  name='admin_users_list'),
    path('admin/users/<str:pk>/', AdminUserDetailView.as_view(), name='admin_user_detail'),
    path('token/refresh/',  TokenRefreshView.as_view(),   name='token_refresh'),
    path('auth/google/',    GoogleAuthView.as_view(),     name='google_auth'),

    path('me/',              MeView.as_view(),             name='me'),
    path('avatar/',          AvatarUploadView.as_view(),   name='avatar_upload'),
    path('accept-terms/',    AcceptTermsView.as_view(),    name='accept_terms'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('delete-account/',  DeleteAccountView.as_view(),  name='delete_account'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/',  ResetPasswordView.as_view(),  name='reset_password'),

    path('location/',         UpdateLocationView.as_view(),  name='update_location'),
    path('location/detect/',  DetectLocationView.as_view(),  name='detect_location'),

    path('profile/<str:username>/', PublicProfileView.as_view(), name='public_profile'),
]
