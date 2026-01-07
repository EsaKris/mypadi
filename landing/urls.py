from django.urls import path
from . import views  # Make sure this import is correct
from .views import PropertyListView, PropertyDetailView

app_name = 'landing'


urlpatterns = [
    path('', views.home, name='home'),
    path('properties/', PropertyListView.as_view(), name='property_list'),
    path('properties/<slug:slug>/', PropertyDetailView.as_view(), name='property_detail'),
]