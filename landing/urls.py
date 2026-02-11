from django.urls import path
from . import views  # Make sure this import is correct
from .views import PropertyListView, PropertyDetailView

app_name = 'landing'


urlpatterns = [
    path('', views.home, name='home'),
    path('properties/', PropertyListView.as_view(), name='property_list'),
    path('properties/<slug:slug>/', PropertyDetailView.as_view(), name='property_detail'),
        # Legal Pages
    path('terms-of-service/', views.TermsOfServiceView.as_view(), name='terms'),
    path('privacy-policy/', views.PrivacyPolicyView.as_view(), name='policy'),
    path('cookie-policy/', views.CookiePolicyView.as_view(), name='cookie'),
    
    # Company Pages
    path('about-us/', views.AboutUsView.as_view(), name='about'),
    path('contact-us/', views.ContactView.as_view(), name='contact'),
]