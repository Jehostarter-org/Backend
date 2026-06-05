from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='portal_dashboard'),
    path('login/', views.login_page, name='portal_login'),
    path('register/', views.register_page, name='portal_register'),
    path('shops/', views.shops_page, name='portal_shops'),
    path('users/', views.users_page, name='portal_users'),
]
