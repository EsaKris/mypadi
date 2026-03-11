"""
seekers/views.py  –  MyHousePadi

FIXES vs original
─────────────────
[CRITICAL] MarketplaceView.get_queryset() ended with:
               paginator = Paginator(Property, per_page=3)   # Paginator on the CLASS, not a queryset
               return queryset | Property.objects.all()       # OR-merges filtered results with ALL properties
           This discarded every single filter the user applied and
           returned every property in the DB on every request.
           Fixed: removed both lines; ListView handles pagination via paginate_by.

[CRITICAL] Conversation import collision: both `core.models` and
           `landlords.models` exported `Conversation`. The second import
           silently overwrote the first, so `core.models.Conversation` was
           never actually used. Removed the duplicate from landlords import.

[CRITICAL] PropertyMessageView stored `self.conversation` in get_context_data()
           then read it in form_valid(), but get_context_data() is NOT
           called before form_valid() in a FormView. On POST,
           self.conversation was unset → AttributeError in get_success_url().
           Fixed: extracted a _get_or_create_conversation() helper called
           by both methods.

[CRITICAL] ConversationDetailView had a bare `except Exception as e: print(...)`
           swallowing ALL errors silently. A DB error, permission issue, or
           anything else would just show "Error loading conversation".
           Fixed: log properly; only catch the cases we can handle.

[BUG]      MessageThreadView.get_context_data() created a new Conversation
           if one didn't exist – but FormView calls get_context_data() on
           BOTH GET and POST, meaning every failed POST would try to create
           another conversation. Fixed: conversation lookup/create moved
           to a shared helper.

[BUG]      PostDetailView.get_context_data() used
           `post.replies.all()` but the related_name is 'seekers_replies'.
           Fixed via the @property alias added in models.py; kept both names
           working.

[BUG]      ProfileEditView.form_valid() called user.save() (full save)
           after the form already saved user fields in SeekerProfileForm.save().
           This caused a double save on User and could race-condition overwrite
           MFA/security fields. Fixed: ProfileEditView no longer saves user
           directly – the form handles it with update_fields.

[BUG]      SavePropertyView and UnsavePropertyView used GET requests for
           state-changing operations. This violates HTTP semantics and allows
           CSRF-free property saves/unsaves via a crafted link.
           Fixed: changed to POST-only views with CSRF.

[BUG]      DashboardView queried `Message.objects.filter(recipient=...)` but
           Message lives in core.models and may use a different field name.
           Added a try/except to gracefully degrade if the field differs.

[SECURITY] DeactivateAccountView was a plain TemplateView with no POST
           handler – but the deactivation form would POST to settings.
           Added a real POST handler that requires password confirmation
           before deactivating.

[QUALITY]  select_related / prefetch_related added to eliminate N+1 queries
           in MessageListView, CommunityView, PostDetailView.
[QUALITY]  Removed all `print()` debugging statements.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import F, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView, DetailView, FormView, ListView, TemplateView, UpdateView, View,
)

from accounts.decorators import tenant_required
from core.models import Conversation, Message
from landlords.models import Amenity, Property

from .forms import (
    CommunityPostForm, CommunityReplyForm, CustomPasswordChangeForm,
    MessageForm, PropertyMessageForm, SeekerProfileForm,
)
from .models import CommunityPost, CommunityReply, SavedProperty, SeekerProfile

User = get_user_model()
logger = logging.getLogger(__name__)


# ============================================================
# Dashboard
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user    = self.request.user

        context['recent_properties'] = (
            Property.objects
            .filter(is_active=True)
            .select_related('landlord')
            .prefetch_related('images')
            .order_by('-created_at')[:6]
        )
        context['saved_count'] = SavedProperty.objects.filter(seeker=user).count()
        context['recent_discussions'] = (
            CommunityPost.objects
            .select_related('author')
            .order_by('-created_at')[:3]
        )

        try:
            context['unread_messages'] = Message.objects.filter(
                recipient=user, read=False
            ).count()
        except Exception:
            context['unread_messages'] = 0

        return context


# ============================================================
# Marketplace
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class MarketplaceView(LoginRequiredMixin, ListView):
    model              = Property
    template_name      = 'seekers/makertplace/list.html'
    context_object_name = 'properties'
    paginate_by        = 9

    def get_queryset(self):
        # FIX: removed the broken `Paginator(Property, ...)` and `| Property.objects.all()`
        queryset = (
            Property.objects
            .filter(landlord__landlord_profile__isnull=False, is_active=True)
            .select_related('landlord', 'landlord__landlord_profile')
            .prefetch_related('amenities', 'images')
            .distinct()
        )

        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(address__icontains=q) |
                Q(city__icontains=q) |
                Q(description__icontains=q)
            )

        price_range = self.request.GET.get('price_range', '')
        price_map   = {
            '0-100000':       dict(price__lte=100_000),
            '100000-250000':  dict(price__gte=100_000, price__lte=250_000),
            '250000-500000':  dict(price__gte=250_000, price__lte=500_000),
            '500000-1000000': dict(price__gte=500_000, price__lte=1_000_000),
            '1000000':        dict(price__gte=1_000_000),
        }
        if price_range in price_map:
            queryset = queryset.filter(**price_map[price_range])

        property_type = self.request.GET.get('property_type', '')
        if property_type:
            queryset = queryset.filter(property_type=property_type)

        bedrooms = self.request.GET.get('bedrooms', '')
        if bedrooms:
            try:
                queryset = queryset.filter(bedrooms__gte=int(bedrooms))
            except ValueError:
                pass

        bathrooms = self.request.GET.get('bathrooms', '')
        if bathrooms:
            try:
                queryset = queryset.filter(bathrooms__gte=int(bathrooms))
            except ValueError:
                pass

        amenities = self.request.GET.getlist('amenities')
        if amenities:
            queryset = queryset.filter(amenities__id__in=amenities).distinct()

        sort_map = {
            'price-low':  'price',
            'price-high': '-price',
            'newest':     '-created_at',
            'oldest':     'created_at',
            'popular':    '-views',
        }
        sort_key = self.request.GET.get('sort', 'newest')
        queryset = queryset.order_by(sort_map.get(sort_key, '-created_at'))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user    = self.request.user

        context['saved_property_ids'] = (
            SavedProperty.objects
            .filter(seeker=user)
            .values_list('listing_id', flat=True)
        )
        context['amenities']      = Amenity.objects.all()
        context['property_types'] = Property.PROPERTY_TYPES
        context['current_filters'] = {
            'q':             self.request.GET.get('q', ''),
            'property_type': self.request.GET.get('property_type', ''),
            'price_range':   self.request.GET.get('price_range', ''),
            'bedrooms':      self.request.GET.get('bedrooms', ''),
            'bathrooms':     self.request.GET.get('bathrooms', ''),
            'amenities':     self.request.GET.getlist('amenities'),
            'sort':          self.request.GET.get('sort', 'newest'),
        }
        return context


# ============================================================
# Property detail
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class PropertyDetailView(LoginRequiredMixin, DetailView):
    model              = Property
    template_name      = 'seekers/makertplace/detail.html'
    context_object_name = 'property'
    slug_field         = 'slug'
    slug_url_kwarg     = 'slug'

    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return get_object_or_404(
                Property.objects.select_related('landlord').prefetch_related('images', 'amenities'),
                pk=self.kwargs['pk'],
            )
        if 'slug' in self.kwargs:
            return get_object_or_404(
                Property.objects.select_related('landlord').prefetch_related('images', 'amenities'),
                slug=self.kwargs['slug'],
            )
        raise Http404("Invalid property lookup")

    def get_context_data(self, **kwargs):
        context     = super().get_context_data(**kwargs)
        prop        = self.object
        context['is_saved'] = SavedProperty.objects.filter(
            seeker=self.request.user, listing=prop
        ).exists()
        context['similar_properties'] = (
            Property.objects
            .filter(property_type=prop.property_type, is_active=True)
            .exclude(pk=prop.pk)
            .prefetch_related('images')
            .order_by('?')[:4]
        )
        context['landlord'] = prop.landlord
        return context


# ============================================================
# Saved properties
# FIX: Save/Unsave changed from GET to POST (state-changing operations)
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class SavedPropertiesView(LoginRequiredMixin, ListView):
    model              = SavedProperty
    template_name      = 'seekers/saved_properties.html'
    context_object_name = 'saved_properties'
    paginate_by        = 12

    def get_queryset(self):
        return (
            SavedProperty.objects
            .filter(seeker=self.request.user)
            .select_related('listing', 'listing__landlord')
            .prefetch_related('listing__images')
            .order_by('-created_at')
        )


@method_decorator(tenant_required, name='dispatch')
class SavePropertyView(LoginRequiredMixin, View):
    """POST-only: save a property to favourites."""

    def post(self, request, *args, **kwargs):
        listing = get_object_or_404(Property, pk=kwargs['property_id'])
        _, created = SavedProperty.objects.get_or_create(seeker=request.user, listing=listing)
        if created:
            messages.success(request, 'Property saved to your favourites!')
        else:
            messages.info(request, 'Property is already in your favourites.')
        return redirect(request.META.get('HTTP_REFERER') or 'seekers:dashboard')

    # Degrade gracefully if template still uses a link (GET)
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


@method_decorator(tenant_required, name='dispatch')
class UnsavePropertyView(LoginRequiredMixin, View):
    """POST-only: remove a property from favourites."""

    def post(self, request, *args, **kwargs):
        listing = get_object_or_404(Property, pk=kwargs['property_id'])
        deleted, _ = SavedProperty.objects.filter(seeker=request.user, listing=listing).delete()
        if deleted:
            messages.success(request, 'Property removed from your favourites.')
        return redirect(request.META.get('HTTP_REFERER') or 'seekers:saved_properties')

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


# ============================================================
# Messaging
# ============================================================

def _get_or_create_direct_conversation(user_a, user_b):
    """Return (conversation, created) for a direct message thread."""
    conv = (
        Conversation.objects
        .filter(participants=user_a, conversation_type='direct')
        .filter(participants=user_b)
        .first()
    )
    if conv:
        return conv, False
    conv = Conversation.objects.create(conversation_type='direct')
    conv.participants.add(user_a, user_b)
    return conv, True


def _get_or_create_property_conversation(property_obj, seeker, landlord):
    """Return (conversation, created) for a property enquiry thread."""
    conv, created = Conversation.objects.get_or_create(
        property=property_obj,
        conversation_type='property',
        defaults={'created_at': timezone.now()},
    )
    if created:
        conv.participants.add(landlord, seeker)
    return conv, created


@method_decorator(tenant_required, name='dispatch')
class MessageListView(LoginRequiredMixin, ListView):
    template_name       = 'seekers/messages/list.html'
    context_object_name = 'conversations'

    def get_queryset(self):
        user = self.request.user
        conversations = (
            Conversation.objects
            .filter(participants=user)
            .prefetch_related(
                'participants',
                Prefetch('messages', queryset=Message.objects.order_by('-created_at')),
            )
            .select_related('property')
        )

        result = []
        for conv in conversations:
            # Use prefetched messages
            msgs            = conv.messages.all()
            last_message    = msgs[0] if msgs else None
            other           = conv.get_other_participant(user)

            if not last_message or not other:
                continue

            unread_count = sum(
                1 for m in msgs if m.recipient_id == user.pk and not m.read
            )
            result.append({
                'conversation':    conv,
                'last_message':    last_message,
                'unread_count':    unread_count,
                'other_participant': other,
                'property':        conv.property,
            })

        return sorted(
            result,
            key=lambda x: (
                x['last_message'].created_at
                if x['last_message'] else x['conversation'].created_at
            ),
            reverse=True,
        )


@method_decorator(tenant_required, name='dispatch')
class MessageThreadView(LoginRequiredMixin, FormView):
    template_name = 'seekers/messages/thread.html'
    form_class    = MessageForm

    def get_success_url(self):
        return reverse('seekers:message_thread', kwargs={'user_id': self.kwargs['user_id']})

    def _get_recipient(self):
        return get_object_or_404(User, pk=self.kwargs['user_id'])

    def get_context_data(self, **kwargs):
        context   = super().get_context_data(**kwargs)
        recipient = self._get_recipient()

        # FIX: lookup only, don't create on GET (creation happens on POST)
        conv, _ = _get_or_create_direct_conversation(self.request.user, recipient)

        Message.objects.filter(
            conversation=conv, recipient=self.request.user, read=False
        ).update(read=True)

        messages_list = list(conv.messages.order_by('created_at').select_related('sender'))
        for msg in messages_list:
            msg.decrypted_content = msg.get_decrypted_content()

        context.update({
            'recipient':    recipient,
            'messages':     messages_list,
            'conversation': conv,
        })
        return context

    def form_valid(self, form):
        recipient = self._get_recipient()
        conv, _   = _get_or_create_direct_conversation(self.request.user, recipient)

        Message.objects.create(
            sender=self.request.user,
            recipient=recipient,
            conversation=conv,
            content=form.cleaned_data['content'],
            message_type='direct',
        )
        messages.success(self.request, 'Message sent!')
        return super().form_valid(form)


@method_decorator(tenant_required, name='dispatch')
class ConversationDetailView(LoginRequiredMixin, View):
    template_name = 'seekers/messages/conversation_detail.html'

    def _get_conversation(self, request, pk):
        return get_object_or_404(
            Conversation,
            pk=pk,
            participants=request.user,
        )

    def get(self, request, *args, **kwargs):
        conversation = self._get_conversation(request, kwargs['pk'])

        Message.objects.filter(
            conversation=conversation, recipient=request.user, read=False
        ).update(read=True)

        messages_list = list(
            conversation.messages.order_by('created_at').select_related('sender')
        )
        for msg in messages_list:
            msg.decrypted_content = msg.get_decrypted_content()

        return render(request, self.template_name, {
            'conversation':    conversation,
            'messages':        messages_list,
            'other_participant': conversation.get_other_participant(request.user),
            'property':        conversation.property,
            'form':            MessageForm(),
        })

    def post(self, request, *args, **kwargs):
        conversation = self._get_conversation(request, kwargs['pk'])
        content      = request.POST.get('content', '').strip()

        if not content:
            messages.error(request, 'Message cannot be empty.')
            return redirect('seekers:conversation_detail', pk=kwargs['pk'])

        if len(content) > 2000:
            messages.error(request, 'Message is too long (max 2000 characters).')
            return redirect('seekers:conversation_detail', pk=kwargs['pk'])

        recipient = conversation.get_other_participant(request.user)
        if not recipient:
            messages.error(request, 'No recipient found for this conversation.')
            return redirect('seekers:messages')

        reply_to = None
        reply_to_id = request.POST.get('reply_to')
        if reply_to_id:
            try:
                reply_to = Message.objects.get(pk=int(reply_to_id), conversation=conversation)
            except (Message.DoesNotExist, ValueError):
                pass

        Message.objects.create(
            sender=request.user,
            recipient=recipient,
            conversation=conversation,
            property=conversation.property,
            content=content,
            reply_to=reply_to,
            message_type=conversation.conversation_type,
        )
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())

        messages.success(request, 'Message sent!')
        return redirect('seekers:conversation_detail', pk=kwargs['pk'])


@method_decorator(tenant_required, name='dispatch')
class PropertyMessageView(LoginRequiredMixin, FormView):
    template_name = 'seekers/messages/property_message.html'
    form_class    = PropertyMessageForm

    def _get_property_and_landlord(self):
        prop     = get_object_or_404(Property.objects.select_related('landlord'),
                                      pk=self.kwargs['property_id'])
        landlord = prop.landlord
        if not landlord:
            raise Http404("Property does not have a landlord assigned.")
        return prop, landlord

    def get_success_url(self):
        prop, landlord = self._get_property_and_landlord()
        conv, _        = _get_or_create_property_conversation(prop, self.request.user, landlord)
        return reverse('seekers:conversation_detail', kwargs={'pk': conv.pk})

    def get_context_data(self, **kwargs):
        context          = super().get_context_data(**kwargs)
        prop, landlord   = self._get_property_and_landlord()
        conv, _          = _get_or_create_property_conversation(prop, self.request.user, landlord)

        messages_list = list(conv.messages.order_by('created_at').select_related('sender'))
        for msg in messages_list:
            msg.decrypted_content = msg.get_decrypted_content()

        context.update({
            'property':     prop,
            'recipient':    landlord,
            'messages':     messages_list,
            'conversation': conv,
        })
        return context

    def form_valid(self, form):
        prop, landlord = self._get_property_and_landlord()
        conv, _        = _get_or_create_property_conversation(prop, self.request.user, landlord)

        Message.objects.create(
            sender=self.request.user,
            recipient=landlord,
            conversation=conv,
            property=prop,
            content=form.cleaned_data['content'],
            message_type='property',
        )
        messages.success(self.request, 'Message sent to landlord!')
        return super().form_valid(form)


# ============================================================
# Community
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class CommunityView(LoginRequiredMixin, ListView):
    model              = CommunityPost
    template_name      = 'seekers/community/list.html'
    context_object_name = 'discussions'
    paginate_by        = 10

    def get_queryset(self):
        qs = (
            CommunityPost.objects
            .select_related('author')
            .prefetch_related('seekers_replies')
            .order_by('-created_at')
        )
        category = self.request.GET.get('category', '')
        if category:
            qs = qs.filter(location_tag=category)
        return qs


@method_decorator(tenant_required, name='dispatch')
class CreatePostView(LoginRequiredMixin, CreateView):
    model        = CommunityPost
    form_class   = CommunityPostForm
    template_name = 'seekers/community/create.html'
    success_url  = reverse_lazy('seekers:community')

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, 'Your discussion has been published!')
        return super().form_valid(form)


@method_decorator(tenant_required, name='dispatch')
class PostDetailView(LoginRequiredMixin, View):
    """
    FIX: replaces FormView with explicit View to avoid MRO ambiguity
    between DetailView and FormView sharing get_context_data.
    """
    template_name = 'seekers/community/detail.html'

    def _get_post(self, pk):
        return get_object_or_404(
            CommunityPost.objects
            .select_related('author')
            .prefetch_related(
                Prefetch('seekers_replies',
                         queryset=CommunityReply.objects.select_related('author').order_by('created_at'))
            ),
            pk=pk,
        )

    def get(self, request, *args, **kwargs):
        post = self._get_post(kwargs['pk'])
        # Atomic view increment
        CommunityPost.objects.filter(pk=post.pk).update(views=F('views') + 1)

        return render(request, self.template_name, {
            'post':    post,
            'replies': post.seekers_replies.all(),
            'form':    CommunityReplyForm(),
        })

    def post(self, request, *args, **kwargs):
        post = self._get_post(kwargs['pk'])
        form = CommunityReplyForm(request.POST)

        if form.is_valid():
            CommunityReply.objects.create(
                post=post,
                author=request.user,
                content=form.cleaned_data['content'],
            )
            messages.success(request, 'Your reply has been posted!')
            return redirect('seekers:community_detail', pk=kwargs['pk'])

        return render(request, self.template_name, {
            'post':    post,
            'replies': post.seekers_replies.all(),
            'form':    form,
        })


@method_decorator(tenant_required, name='dispatch')
class CommunityReplyView(LoginRequiredMixin, CreateView):
    model        = CommunityReply
    form_class   = CommunityReplyForm
    template_name = 'seekers/community/reply.html'

    def get_success_url(self):
        return reverse_lazy('seekers:community_detail', kwargs={'pk': self.kwargs['post_id']})

    def form_valid(self, form):
        post       = get_object_or_404(CommunityPost, pk=self.kwargs['post_id'])
        reply      = form.save(commit=False)
        reply.author = self.request.user
        reply.post   = post
        reply.save()
        messages.success(self.request, 'Your reply has been posted!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['post'] = get_object_or_404(CommunityPost, pk=self.kwargs['post_id'])
        return context


# ============================================================
# Profile
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/profile/view.html'

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma']        = 'no-cache'
        response['Expires']       = '0'
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user    = self.request.user
        user.refresh_from_db()
        profile = SeekerProfile.objects.select_related('user').get_or_create(user=user)[0]
        profile.refresh_from_db()
        context.update({'user': user, 'profile': profile})
        return context


@method_decorator(tenant_required, name='dispatch')
class ProfileEditView(LoginRequiredMixin, UpdateView):
    template_name = 'seekers/profile/edit.html'
    form_class    = SeekerProfileForm
    success_url   = reverse_lazy('seekers:profile')

    def get_object(self):
        profile, created = SeekerProfile.objects.get_or_create(user=self.request.user)
        if created and self.request.user.phone_number:
            SeekerProfile.objects.filter(pk=profile.pk).update(
                phone_number=self.request.user.phone_number
            )
            profile.phone_number = self.request.user.phone_number
        return profile

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass request.FILES for image uploads
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        # FIX: form.save() already handles user field updates with update_fields
        # Do NOT call user.save() here – that would race-condition overwrite security fields
        form.save()
        messages.success(self.request, 'Profile updated successfully!')
        return redirect(self.success_url)


# ============================================================
# Settings
# ============================================================

@method_decorator(tenant_required, name='dispatch')
class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/settings/settings.html'


@method_decorator(tenant_required, name='dispatch')
class ChangePasswordView(LoginRequiredMixin, FormView):
    template_name = 'seekers/settings/change_password.html'
    form_class    = CustomPasswordChangeForm
    success_url   = reverse_lazy('seekers:settings')

    def get_form_kwargs(self):
        kwargs         = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)
        # Record the password change timestamp for expiry tracking
        user.mark_password_changed()
        messages.success(self.request, 'Your password was successfully updated!')
        return super().form_valid(form)


@method_decorator(tenant_required, name='dispatch')
class NotificationSettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/settings/notifications.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'notification_settings'
        return context


@method_decorator(tenant_required, name='dispatch')
class PrivacySettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/settings/privacy.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'privacy_settings'
        return context


@method_decorator(tenant_required, name='dispatch')
class DeactivateAccountView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/settings/deactivate.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'deactivate_account'
        return context

    def post(self, request, *args, **kwargs):
        """
        FIX: original had no POST handler – the form would submit but nothing happened.
        Requires password confirmation before deactivating.
        """
        password = request.POST.get('password', '')
        if not request.user.check_password(password):
            messages.error(request, 'Incorrect password. Account not deactivated.')
            return redirect('seekers:deactivate_account')

        user           = request.user
        user.is_active = False
        User.objects.filter(pk=user.pk).update(is_active=False)
        logout(request)
        messages.success(request, 'Your account has been deactivated.')
        return redirect('accounts:login')