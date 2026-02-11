from django.shortcuts import redirect, render, get_object_or_404
from django.views.generic import ListView, DetailView
from landlords import models
from landlords.models import Property, Amenity, PropertyImage
from django.core.paginator import Paginator

def home(request):
    # If a user is login direct to dashboard 
    if request.user.is_authenticated:

        if request.user.user_type == 'landlord':
            return redirect('/landlords/')
        
        if request.user.user_type == 'tenant':
            return redirect('/seekers/')
        
        if request.user.user_type == 'admin':
            return redirect('/admin/')
        
    # Get 6 featured properties for the homepage
    featured_properties = Property.objects.filter(
        is_published=True,
        is_active=True
    ).select_related('landlord').prefetch_related('images', 'amenities')[:6]
    
    context = {
        'featured_properties': featured_properties,
    }
    return render(request, 'landing/home.html', context)

class PropertyListView(ListView):
    model = Property
    template_name = 'landing/properties/property_list.html'
    context_object_name = 'properties'
    paginate_by = 12
    
    def get_queryset(self):
        queryset = Property.objects.filter(
            is_published=True,
            is_active=True
        ).select_related('landlord').prefetch_related('images', 'amenities')
        
        # Filter by property type if specified
        property_type = self.request.GET.get('type')
        if property_type:
            queryset = queryset.filter(property_type=property_type)
            
        # Filter by price range if specified
        price_min = self.request.GET.get('price_min')
        price_max = self.request.GET.get('price_max')
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        if price_max:
            queryset = queryset.filter(price__lte=price_max)
            
        # Filter by location if specified
        location = self.request.GET.get('location')
        if location:
            queryset = queryset.filter(
                models.Q(city__icontains=location) |
                models.Q(state__icontains=location) |
                models.Q(address__icontains=location)
            )
            
        return queryset.order_by('-is_featured', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['amenities'] = Amenity.objects.all()
        context['property_types'] = dict(Property.PROPERTY_TYPES)
        return context

class PropertyDetailView(DetailView):
    model = Property
    template_name = 'landing/properties/property_detail.html'
    context_object_name = 'property'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        obj.increment_views()  # Increment view count
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property = self.object
        context['related_properties'] = Property.objects.filter(
            property_type=property.property_type,
            is_published=True,
            is_active=True
        ).exclude(id=property.id).select_related('landlord').prefetch_related('images')[:4]
        return context


from django.shortcuts import render
from django.views.generic import TemplateView

# ============================================
# SIMPLE STATIC PAGE VIEWS - NO CONTEXT NEEDED
# ============================================

class TermsOfServiceView(TemplateView):
    """Terms of Service page"""
    template_name = 'landing/terms.html'


class PrivacyPolicyView(TemplateView):
    """Privacy Policy page"""
    template_name = 'landing/policy.html'


class CookiePolicyView(TemplateView):
    """Cookie Policy page"""
    template_name = 'landing/cookie.html'


class AboutUsView(TemplateView):
    """About Us page"""
    template_name = 'landing/about.html'


class ContactView(TemplateView):
    """Contact page"""
    template_name = 'landing/contact.html'