"""
seekers/admin.py  –  MyHousePadi

FIXES vs original
─────────────────
[BUG]  Original registered `Message` from `core.models` inside this app's
       admin.py. This is wrong for two reasons:
       1. Message belongs to core – its admin should live in core/admin.py.
       2. If core/admin.py also registers Message, Django raises
          AlreadyRegistered at startup.
       Removed the Message registration. Register it in core/admin.py.

[BUG]  SavedPropertyAdmin used `search_fields = ('seeker__username', 'property__title')`
       but the field is now `listing` (renamed in models.py). Updated.

[QUALITY] Added list_per_page and date_hierarchy for large tables.
"""

from django.contrib import admin

from .models import CommunityPost, CommunityReply, SavedProperty, SeekerProfile


@admin.register(SeekerProfile)
class SeekerProfileAdmin(admin.ModelAdmin):
    list_display   = ('user', 'verified', 'phone_verified', 'employment_status', 'created_at')
    list_filter    = ('verified', 'phone_verified', 'employment_status', 'gender')
    search_fields  = ('user__email', 'user__first_name', 'user__last_name', 'phone_number')
    raw_id_fields  = ('user',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page  = 50
    date_hierarchy = 'created_at'


@admin.register(SavedProperty)
class SavedPropertyAdmin(admin.ModelAdmin):
    list_display  = ('seeker', 'listing', 'created_at')
    list_filter   = ('created_at',)
    # FIX: field renamed from `property` to `listing` in models.py
    search_fields = ('seeker__username', 'listing__title')
    raw_id_fields = ('seeker', 'listing')
    list_per_page = 50


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display   = ('title', 'author', 'views', 'upvotes', 'created_at')
    list_filter    = ('created_at', 'location_tag')
    search_fields  = ('title', 'author__username', 'content')
    raw_id_fields  = ('author',)
    readonly_fields = ('views', 'upvotes', 'created_at', 'updated_at')
    list_per_page  = 50
    date_hierarchy = 'created_at'


@admin.register(CommunityReply)
class CommunityReplyAdmin(admin.ModelAdmin):
    list_display  = ('post', 'author', 'created_at')
    list_filter   = ('created_at',)
    search_fields = ('post__title', 'author__username')
    raw_id_fields = ('post', 'author')
    list_per_page = 50
    date_hierarchy = 'created_at'