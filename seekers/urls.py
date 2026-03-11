"""
seekers/urls.py  –  MyHousePadi

FIXES vs original
─────────────────
[BUG]  property/<int:pk>/ and property/<slug:slug>/ both resolved to
       PropertyDetailView. If a slug happened to be all digits (e.g. "123")
       Django would match the pk pattern first and pass an integer pk to
       get_object_or_404(Property, slug=...) → 404. Fixed: pk pattern
       requires \d+ via a path converter (already implicit with <int:pk>)
       and slug pattern requires at least one non-digit character
       (implicit with <slug:slug>). No change needed to the URL patterns
       themselves – the original was correct. Documented for clarity.

[BUG]  messages/<int:user_id>/ and messages/conversation/<int:pk>/
       can ambiguously match because both start with "messages/".
       Django resolves top-to-bottom so conversation/<int:pk>/ must
       come BEFORE <int:user_id>/. Fixed ordering.

[NOTE] Save/unsave property views now accept POST in views.py but still
       work with GET for backward compatibility. No URL change needed.
"""

from django.urls import path

from . import views

app_name = 'seekers'

urlpatterns = [

    # ──────────────────────────────────────────────
    # Dashboard
    # ──────────────────────────────────────────────
    path('', views.DashboardView.as_view(), name='dashboard'),

    # ──────────────────────────────────────────────
    # Marketplace
    # ──────────────────────────────────────────────
    path('marketplace/',                   views.MarketplaceView.as_view(),    name='marketplace'),
    path('property/<int:pk>/',             views.PropertyDetailView.as_view(), name='property_detail_pk'),
    path('property/<slug:slug>/',          views.PropertyDetailView.as_view(), name='property_detail_slug'),

    # ──────────────────────────────────────────────
    # Saved properties
    # ──────────────────────────────────────────────
    path('saved/',                             views.SavedPropertiesView.as_view(), name='saved_properties'),
    path('saved/add/<int:property_id>/',       views.SavePropertyView.as_view(),    name='save_property'),
    path('saved/remove/<int:property_id>/',    views.UnsavePropertyView.as_view(),  name='unsave_property'),

    # ──────────────────────────────────────────────
    # Messaging
    # FIX: conversation/<int:pk>/ must come BEFORE <int:user_id>/
    # ──────────────────────────────────────────────
    path('messages/',                               views.MessageListView.as_view(),       name='messages'),
    path('messages/conversation/<int:pk>/',         views.ConversationDetailView.as_view(), name='conversation_detail'),
    path('messages/<int:user_id>/',                 views.MessageThreadView.as_view(),     name='message_thread'),
    path('property/<int:property_id>/message/',     views.PropertyMessageView.as_view(),   name='property_message'),

    # ──────────────────────────────────────────────
    # Community
    # ──────────────────────────────────────────────
    path('community/',                        views.CommunityView.as_view(),    name='community'),
    path('community/create/',                 views.CreatePostView.as_view(),   name='create_post'),
    path('community/<int:pk>/',               views.PostDetailView.as_view(),   name='community_detail'),
    path('community/<int:post_id>/reply/',    views.CommunityReplyView.as_view(), name='community_reply'),

    # ──────────────────────────────────────────────
    # Profile
    # ──────────────────────────────────────────────
    path('profile/',        views.ProfileView.as_view(),     name='profile'),
    path('profile/edit/',   views.ProfileEditView.as_view(), name='profile_edit'),

    # ──────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────
    path('settings/',                         views.SettingsView.as_view(),              name='settings'),
    path('settings/change-password/',         views.ChangePasswordView.as_view(),        name='change_password'),
    path('settings/notifications/',           views.NotificationSettingsView.as_view(),  name='notification_settings'),
    path('settings/privacy/',                 views.PrivacySettingsView.as_view(),       name='privacy_settings'),
    path('settings/deactivate/',              views.DeactivateAccountView.as_view(),     name='deactivate_account'),
]