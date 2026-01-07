from django.contrib.auth.decorators import login_required
from django.urls import path
from . import views


app_name = 'landlords'

# Regular landlord URLs (for property owners)
urlpatterns = [
    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),
    
    # Properties
    path('properties/', views.PropertyListView.as_view(), name='properties'),
    path('properties/add/', views.PropertyCreateView.as_view(), name='property_create'),
    path('properties/<int:pk>/', views.PropertyDetailView.as_view(), name='property_detail'),
    path('properties/<int:pk>/edit/', views.PropertyUpdateView.as_view(), name='property_edit'),
    path('properties/<int:pk>/edit/', views.PropertyEditView.as_view(), name='property_edit'),
    
    # Tenants
    path('tenants/', views.TenantListView.as_view(), name='tenants'),
    path('tenants/add/<int:property_id>/', views.TenantCreateView.as_view(), name='tenant_create'),
    path('tenants/<int:pk>/edit/', views.TenantUpdateView.as_view(), name='tenant_edit'),
    
    # Applications
    path('applications/', views.RentalApplicationListView.as_view(), name='applications'),
    path('applications/<int:pk>/', views.RentalApplicationDetailView.as_view(), name='application_detail'),
    
    # Leases
    path('leases/add/<int:tenant_id>/', views.LeaseAgreementCreateView.as_view(), name='lease_create'),
    
    # Maintenance
    path('maintenance/', views.MaintenanceRequestListView.as_view(), name='maintenance'),
    path('maintenance/<int:pk>/', views.MaintenanceRequestDetailView.as_view(), name='maintenance_detail'),
    
    # Finances
    path('payments/', views.PaymentListView.as_view(), name='payments'),
    path('payments/add/<int:tenant_id>/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('expenses/', views.ExpenseListView.as_view(), name='expenses'),
    path('expenses/add/<int:property_id>/', views.ExpenseCreateView.as_view(), name='expense_create'),
    
    # Conversations
    path('messages/', views.MessagesView.as_view(), name='messages'),
    path('messages/send/', views.send_message, name='send_message'),
    path('messages/mark-read/<int:conversation_id>/', views.mark_as_read, name='mark_as_read'),

    
    # Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    path('finances/', views.FinancesView.as_view(), name='finances'),
    path('settings/', views.SettingsView.as_view(), name='settings'),

    # Community
    path('community/', login_required(views.CommunityView.as_view()), name='community'),
    path('community/create/', login_required(views.CreatePostView.as_view()), name='create_post'),
    path('community/<int:pk>/', login_required(views.PostDetailView.as_view()), name='community_detail'),
    path('community/<int:pk>/edit/', login_required(views.EditPostView.as_view()), name='edit_post'),
    path('community/<int:pk>/delete/', login_required(views.DeletePostView.as_view()), name='delete_post'),
    path('community/<int:post_id>/reply/', login_required(views.CommunityReplyView.as_view()), name='post_reply'),
]

