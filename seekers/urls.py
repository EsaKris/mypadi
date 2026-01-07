from django.urls import path
from . import views

app_name = 'seekers'

urlpatterns = [
    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),
    
    # Marketplace
    path('marketplace/', views.MarketplaceView.as_view(), name='marketplace'),
    path('property/<int:pk>/', views.PropertyDetailView.as_view(), name='property_detail_pk'),
    path('property/<slug:slug>/', views.PropertyDetailView.as_view(), name='property_detail_slug'),
    
    # Saved Properties
    path('saved/', views.SavedPropertiesView.as_view(), name='saved_properties'),
    path('saved/add/<int:property_id>/', views.SavePropertyView.as_view(), name='save_property'),
    path('saved/remove/<int:property_id>/', views.UnsavePropertyView.as_view(), name='unsave_property'),
    
    # Messaging
    path('messages/', views.MessageListView.as_view(), name='messages'),
    path('messages/conversation/<int:pk>/', views.ConversationDetailView.as_view(), name='conversation_detail'),
    path('messages/<int:user_id>/', views.MessageThreadView.as_view(), name='message_thread'),
    # path('messages/property/<int:property_id>/', views.PropertyMessageView.as_view(), name='property_message'),
    path('property/<int:property_id>/message/', views.PropertyMessageView.as_view(), name='property_message'),

    # Community
    path('community/', views.CommunityView.as_view(), name='community'),
    path('community/create/', views.CreatePostView.as_view(), name='create_post'),
    path('community/<int:pk>/', views.PostDetailView.as_view(), name='community_detail'),
    path('community/<int:post_id>/reply/', views.CommunityReplyView.as_view(), name='community_reply'),
    # path('community/<int:pk>/edit/', views.EditPostView.as_view(), name='edit_post'),
    # path('community/<int:pk>/delete/', views.DeletePostView.as_view(), name='delete_post'),
    
    # Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    
    # Settings
    path('settings/', views.SettingsView.as_view(), name='settings'),
    path('settings/change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    path('settings/notifications/', views.NotificationSettingsView.as_view(), name='notification_settings'),
    path('settings/privacy/', views.PrivacySettingsView.as_view(), name='privacy_settings'),
    path('settings/deactivate/', views.DeactivateAccountView.as_view(), name='deactivate_account'),
]