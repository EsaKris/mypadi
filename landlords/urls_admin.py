# landlords/urls_admin.py
from django.urls import path
from .admin_views import (
    AdminDashboardView,
    AdminDetailView,
    AdminLoginView,
    CreateAdminView,
    AdminListView,
    PromoteToSuperAdminView,
    PropertyApprovalListView, 
    property_approval_detail,
    LandlordVerificationListView, 
    landlord_verification_detail,
    LandlordListView, 
    LandlordDetailView, 
    toggle_landlord_status, CombinedAnalyticsView, export_combined_report,
    DocumentVerificationListView, 
    verify_documents,AdminProfileView, AdminSettingsView, NotificationListView, mark_notification_as_read, 
    mark_all_notifications_as_read, CreateNotificationView, AdminLogoutView
)
from seekers.admin_views import (
    SeekerListView, 
    SeekerDetailView, 
    toggle_seeker_status
)
app_name = 'landlords_admin'
urlpatterns = [
    path('', AdminDashboardView.as_view(), name='dashboard'),  # Changed from 'admin_dashboard'
    path('login/', AdminLoginView.as_view(), name='login'),
    path('logout/', AdminLogoutView.as_view(), name='logout'),
    path('create-admin/', CreateAdminView.as_view(), name='create_admin'),
    path('admin-list/', AdminListView.as_view(), name='admin_list'),
    path('promote-to-superadmin/<int:pk>/', PromoteToSuperAdminView.as_view(), 
         name='promote_to_superadmin'),
    path('admin-detail/<int:pk>/', AdminDetailView.as_view(), name='admin_detail'),
    path('properties/', PropertyApprovalListView.as_view(), name='property_approvals'),
    path('properties/<int:pk>/', property_approval_detail, name='property_approval_detail'),
    path('landlords/', LandlordVerificationListView.as_view(), name='landlord_verifications'),
    path('landlords/<int:pk>/', landlord_verification_detail, name='landlord_verification_detail'),
    path('all-landlords/', LandlordListView.as_view(), name='landlord_list'),
    path('all-landlords/<int:pk>/', LandlordDetailView.as_view(), name='landlord_detail'),
    path('all-landlords/<int:pk>/toggle-status/', toggle_landlord_status, name='toggle_landlord_status'),
    path('documents/', DocumentVerificationListView.as_view(), name='document_verifications'),
    path('documents/<int:pk>/verify/', verify_documents, name='verify_documents'),
    path('seekers/', SeekerListView.as_view(), name='seeker_list'),
    path('seekers/<int:pk>/', SeekerDetailView.as_view(), name='seeker_detail'),
    path('seekers/<int:pk>/toggle-status/', toggle_seeker_status, name='toggle_seeker_status'),
    path('profile/', AdminProfileView.as_view(), name='admin_profile'),
    path('settings/', AdminSettingsView.as_view(), name='admin_settings'),
    path('analytics/', CombinedAnalyticsView.as_view(), name='combined_analytics'),
    path('analytics/export/', export_combined_report, name='export_combined_report'),
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/read/', mark_notification_as_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', mark_all_notifications_as_read, name='mark_all_notifications_read'),
    path('notifications/create/', CreateNotificationView.as_view(), name='create_notification'),

]