from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='portal_dashboard'),
    path('login/', views.login_page, name='portal_login'),
    path('register/', views.register_page, name='portal_register'),
    path('shops/', views.shops_page, name='portal_shops'),
    path('support/', views.support_page, name='portal_support'),
    path('providers/', views.providers_page, name='portal_providers'),
    path('eligibility/', views.eligibility_page, name='portal_eligibility'),
    path('communities/', views.communities_page, name='portal_communities'),
    path('users/', views.users_page, name='portal_users'),
]
