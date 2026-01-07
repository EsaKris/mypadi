from django.contrib import admin
from .models import SeekerProfile, SavedProperty, CommunityPost, CommunityReply
from core.models import Conversation, Message

@admin.register(SeekerProfile)
class SeekerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'verified', 'phone_verified', 'employment_status', 'created_at')
    list_filter = ('verified', 'phone_verified', 'employment_status', 'gender')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'phone_number')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(SavedProperty)
class SavedPropertyAdmin(admin.ModelAdmin):
    list_display = ('seeker', 'property', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('seeker__username', 'property__title')
    raw_id_fields = ('seeker', 'property')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'property', 'read', 'created_at')
    list_filter = ('read', 'created_at')
    search_fields = ('sender__username', 'recipient__username', 'property__title')
    raw_id_fields = ('sender', 'recipient', 'property')

@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'views', 'upvotes', 'created_at')
    list_filter = ('created_at', 'location_tag')
    search_fields = ('title', 'author__username', 'content')
    raw_id_fields = ('author',)

@admin.register(CommunityReply)
class CommunityReplyAdmin(admin.ModelAdmin):
    list_display = ('post', 'author', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('post__title', 'author__username')
    raw_id_fields = ('post', 'author')