from django.urls import path
from .views import (
    ServiceRequestListCreateView, ServiceRequestDetailView,
    AvailableServicesView, AcceptServiceView, ReviewServiceView,
)

urlpatterns = [
    path('', ServiceRequestListCreateView.as_view(), name='services'),
    path('<str:pk>/', ServiceRequestDetailView.as_view(), name='service_detail'),
    path('available/', AvailableServicesView.as_view(), name='available_services'),
    path('<str:pk>/accept/', AcceptServiceView.as_view(), name='accept_service'),
    path('<str:pk>/review/', ReviewServiceView.as_view(), name='review_service'),
]