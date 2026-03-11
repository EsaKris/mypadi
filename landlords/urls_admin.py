# landlords/urls_admin.py
"""
Admin URL configuration for MyHousePadi.

Fixes & improvements:
- Grouped routes by feature area with comments for readability.
- Fixed notification URL ordering: `mark-all-read/` MUST come before
  `<int:pk>/read/` — otherwise Django matches `mark-all-read` as a pk
  and raises a ValueError trying to cast "mark-all-read" to int.
  Original order had `<int:pk>/read/` first which would shadow it.
- `promote-to-superadmin` only accepts POST (enforced in the view via
  UserPassesTestMixin + View.post()); noted here for clarity.
- All imports kept explicit so missing views cause an ImportError at
  startup (fast failure) rather than a silent 404 at runtime.
"""

from django.urls import path

from .admin_views import (
    # Auth
    AdminLoginView,
    AdminLogoutView,

    # Admin user management
    AdminDashboardView,
    AdminListView,
    AdminDetailView,
    CreateAdminView,
    PromoteToSuperAdminView,

    # Properties
    PropertyApprovalListView,
    property_approval_detail,

    # Landlord verifications
    LandlordVerificationListView,
    landlord_verification_detail,

    # Document verifications
    DocumentVerificationListView,
    verify_documents,

    # All landlords
    LandlordListView,
    LandlordDetailView,
    toggle_landlord_status,

    # Analytics
    CombinedAnalyticsView,
    export_combined_report,

    # Notifications
    NotificationListView,
    mark_notification_as_read,
    mark_all_notifications_as_read,
    CreateNotificationView,

    # Profile & settings
    AdminProfileView,
    AdminSettingsView,
)

from seekers.admin_views import (
    SeekerListView,
    SeekerDetailView,
    toggle_seeker_status,
)

app_name = 'landlords_admin'

urlpatterns = [

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    path('login/', AdminLoginView.as_view(), name='login'),
    path('logout/', AdminLogoutView.as_view(), name='logout'),  # POST only

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    path('', AdminDashboardView.as_view(), name='dashboard'),

    # ------------------------------------------------------------------
    # Admin user management  (superuser only)
    # ------------------------------------------------------------------
    path('admin-list/', AdminListView.as_view(), name='admin_list'),
    path('admin-detail/<int:pk>/', AdminDetailView.as_view(), name='admin_detail'),
    path('create-admin/', CreateAdminView.as_view(), name='create_admin'),
    path('promote-to-superadmin/<int:pk>/', PromoteToSuperAdminView.as_view(),
         name='promote_to_superadmin'),

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    path('properties/', PropertyApprovalListView.as_view(), name='property_approvals'),
    path('properties/<int:pk>/', property_approval_detail, name='property_approval_detail'),

    # ------------------------------------------------------------------
    # Landlord verifications
    # ------------------------------------------------------------------
    path('landlords/', LandlordVerificationListView.as_view(), name='landlord_verifications'),
    path('landlords/<int:pk>/', landlord_verification_detail, name='landlord_verification_detail'),

    # ------------------------------------------------------------------
    # Document verifications
    # ------------------------------------------------------------------
    path('documents/', DocumentVerificationListView.as_view(), name='document_verifications'),
    path('documents/<int:pk>/verify/', verify_documents, name='verify_documents'),

    # ------------------------------------------------------------------
    # All landlords
    # ------------------------------------------------------------------
    path('all-landlords/', LandlordListView.as_view(), name='landlord_list'),
    path('all-landlords/<int:pk>/', LandlordDetailView.as_view(), name='landlord_detail'),
    path('all-landlords/<int:pk>/toggle-status/', toggle_landlord_status,
         name='toggle_landlord_status'),

    # ------------------------------------------------------------------
    # Seekers  (views live in seekers app)
    # ------------------------------------------------------------------
    path('seekers/', SeekerListView.as_view(), name='seeker_list'),
    path('seekers/<int:pk>/', SeekerDetailView.as_view(), name='seeker_detail'),
    path('seekers/<int:pk>/toggle-status/', toggle_seeker_status, name='toggle_seeker_status'),

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    path('analytics/', CombinedAnalyticsView.as_view(), name='combined_analytics'),
    path('analytics/export/', export_combined_report, name='export_combined_report'),

    # ------------------------------------------------------------------
    # Notifications
    # IMPORTANT: `mark-all-read/` MUST be before `<int:pk>/read/`
    # so Django does not try to cast "mark-all-read" as an integer pk.
    # ------------------------------------------------------------------
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/mark-all-read/', mark_all_notifications_as_read,
         name='mark_all_notifications_read'),
    path('notifications/create/', CreateNotificationView.as_view(), name='create_notification'),
    path('notifications/<int:pk>/read/', mark_notification_as_read,
         name='mark_notification_read'),

    # ------------------------------------------------------------------
    # Profile & settings
    # ------------------------------------------------------------------
    path('profile/', AdminProfileView.as_view(), name='admin_profile'),
    path('settings/', AdminSettingsView.as_view(), name='admin_settings'),
]