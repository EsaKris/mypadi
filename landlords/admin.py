# landlords/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import (
    LandlordProfile, Property, RentalApplication, 
    MaintenanceRequest, Payment, Expense
)

User = get_user_model()

@admin.register(LandlordProfile)
class LandlordProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_full_name', 'email', 'is_verified', 'phone_verified', 'created_at')
    list_filter = ('is_verified', 'phone_verified')
    search_fields = ('user__first_name', 'user__last_name', 'user__email')
    actions = ['verify_landlords', 'unverify_landlords']
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('User Info', {
            'fields': ('user', 'get_full_name', 'email')
        }),
        ('Verification', {
            'fields': ('is_verified', 'verification_documents', 'phone_verified', 'phone_verified_date')
        }),
        ('Profile Details', {
            'fields': ('profile_picture', 'phone_number', 'bio', 'company_name', 'business_address')
        }),
        ('Social Media', {
            'fields': ('social_facebook', 'social_twitter', 'social_linkedin', 'social_instagram'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Full Name'
    
    def email(self, obj):
        return obj.user.email
    email.short_description = 'Email'
    
    def verify_landlords(self, request, queryset):
        queryset.update(is_verified=True)
    verify_landlords.short_description = "Verify selected landlords"
    
    def unverify_landlords(self, request, queryset):
        queryset.update(is_verified=False)
    unverify_landlords.short_description = "Unverify selected landlords"

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'landlord', 'city', 'property_type', 'price', 'is_verified', 'is_published', 'created_at')
    list_filter = ('is_verified', 'is_published', 'property_type', 'city')
    search_fields = ('name', 'landlord__first_name', 'landlord__last_name', 'address', 'city')
    actions = ['verify_properties', 'unverify_properties', 'publish_properties', 'unpublish_properties']
    readonly_fields = ('created_at', 'updated_at', 'views')
    raw_id_fields = ('landlord', 'amenities')
    filter_horizontal = ('amenities',)
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('landlord', 'name', 'slug', 'description')
        }),
        ('Location', {
            'fields': ('address', 'city', 'state', 'zip_code')
        }),
        ('Property Details', {
            'fields': ('property_type', 'num_units', 'amenities')
        }),
        ('Pricing', {
            'fields': ('price', 'price_period')
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured', 'is_verified', 'is_published')
        }),
        ('Statistics', {
            'fields': ('views', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def verify_properties(self, request, queryset):
        queryset.update(is_verified=True)
    verify_properties.short_description = "Verify selected properties"
    
    def unverify_properties(self, request, queryset):
        queryset.update(is_verified=False)
    unverify_properties.short_description = "Unverify selected properties"
    
    def publish_properties(self, request, queryset):
        queryset.update(is_published=True)
    publish_properties.short_description = "Publish selected properties"
    
    def unpublish_properties(self, request, queryset):
        queryset.update(is_published=False)
    unpublish_properties.short_description = "Unpublish selected properties"

# Custom admin site for better separation
class LandlordAdminSite(admin.AdminSite):
    site_header = "Landlord Administration"
    site_title = "Landlord Admin Portal"
    index_title = "Welcome to Landlord Administration"

landlord_admin_site = LandlordAdminSite(name='landlord_admin')

# Register models with custom admin site
landlord_admin_site.register(LandlordProfile, LandlordProfileAdmin)
landlord_admin_site.register(Property, PropertyAdmin)
landlord_admin_site.register(RentalApplication)
landlord_admin_site.register(MaintenanceRequest)
landlord_admin_site.register(Payment)
landlord_admin_site.register(Expense)