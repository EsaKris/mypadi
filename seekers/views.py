from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.views.generic import TemplateView, View, ListView, DetailView, CreateView, UpdateView, FormView
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q, F
from django.utils.decorators import method_decorator
from accounts.decorators import tenant_required
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from core.models import Conversation, Message
from landlords.models import Amenity, Property, Conversation
from .models import SeekerProfile, SavedProperty, CommunityPost, CommunityReply
from .forms import (SeekerProfileForm, CommunityPostForm, MessageForm, 
                   PropertyMessageForm, CommunityReplyForm, CustomPasswordChangeForm)

User = get_user_model()

@method_decorator(tenant_required, name='dispatch')
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_properties'] = Property.objects.filter(is_active=True).order_by('-created_at')[:6]
        context['saved_count'] = SavedProperty.objects.filter(seeker=self.request.user).count()
        context['unread_messages'] = Message.objects.filter(
            recipient=self.request.user, 
            read=False
        ).count()
        context['recent_discussions'] = CommunityPost.objects.all().order_by('-created_at')[:3]
        return context

@method_decorator(tenant_required, name='dispatch')
class MarketplaceView(LoginRequiredMixin, ListView):
    model = Property
    template_name = 'seekers/makertplace/list.html'
    context_object_name = 'properties'
    paginate_by = 9

    def get_queryset(self):
        # Base queryset - all active and published properties
        queryset = Property.objects.all().select_related('landlord').prefetch_related(
       
        ).select_related('landlord').prefetch_related(
            'amenities',
            'images'
        )
        # Optional: Filter for landlords with profiles (remove if not needed)
        queryset = queryset.filter(landlord__landlord_profile__isnull=False)

        # Search functionality
        search_query = self.request.GET.get('q')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(address__icontains=search_query) |
                Q(city__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Handle price range from template (combines min/max)
        price_range = self.request.GET.get('price_range')
        if price_range:
            if price_range == "0-100000":
                queryset = queryset.filter(price__lte=100000)
            elif price_range == "100000-250000":
                queryset = queryset.filter(price__gte=100000, price__lte=250000)
            elif price_range == "250000-500000":
                queryset = queryset.filter(price__gte=250000, price__lte=500000)
            elif price_range == "500000-1000000":
                queryset = queryset.filter(price__gte=500000, price__lte=1000000)
            elif price_range == "1000000":
                queryset = queryset.filter(price__gte=1000000)

        # Property type filter
        property_type = self.request.GET.get('property_type')
        if property_type:
            queryset = queryset.filter(property_type=property_type)

        # Bedroom filter
        bedrooms = self.request.GET.get('bedrooms')
        if bedrooms:
            queryset = queryset.filter(bedrooms__gte=bedrooms)

        # Bathroom filter
        bathrooms = self.request.GET.get('bathrooms')
        if bathrooms:
            queryset = queryset.filter(bathrooms__gte=bathrooms)

        # Amenities filter
        amenities = self.request.GET.getlist('amenities')
        if amenities:
            queryset = queryset.filter(amenities__id__in=amenities).distinct()

        # Sorting - matches template options
        sort = self.request.GET.get('sort')
        if sort == 'price-low':
            queryset = queryset.order_by('price')
        elif sort == 'price-high':
            queryset = queryset.order_by('-price')
        elif sort == 'newest':
            queryset = queryset.order_by('-created_at')
        elif sort == 'oldest':
            queryset = queryset.order_by('created_at')
        elif sort == 'popular':  # Example: you might need to implement this
            queryset = queryset.order_by('-views')
        else:  # Default sorting
            queryset = queryset.order_by('-created_at')
        paginator = Paginator(Property, per_page=3)
        return queryset | Property.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Saved properties for the current user
        context['saved_property_ids'] = SavedProperty.objects.filter(
            seeker=self.request.user
        ).values_list('property_id', flat=True)
        
        # All amenities for filter panel
        context['amenities'] = Amenity.objects.all()
        
        # Property types for dropdown
        context['property_types'] = Property.PROPERTY_TYPES
        
        # Current filter state for template
        context['current_filters'] = {
            'q': self.request.GET.get('q', ''),
            'property_type': self.request.GET.get('property_type', ''),
            'price_range': self.request.GET.get('price_range', ''),
            'bedrooms': self.request.GET.get('bedrooms', ''),
            'bathrooms': self.request.GET.get('bathrooms', ''),
            'amenities': self.request.GET.getlist('amenities'),
            'sort': self.request.GET.get('sort', 'newest'),
        }
        
        # Add any other context you need
        return context

@method_decorator(tenant_required, name='dispatch') 
class PropertyDetailView(LoginRequiredMixin, DetailView):
    model = Property
    template_name = 'seekers/makertplace/detail.html'
    context_object_name = 'property'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    
    def get_object(self, queryset=None):
        try:
            if 'pk' in self.kwargs:
                return get_object_or_404(Property, pk=self.kwargs['pk'])
            elif 'slug' in self.kwargs:
                return get_object_or_404(Property, slug=self.kwargs['slug'])
        except Exception as e:
            raise Http404("Property doesn't exist") from e
        raise Http404("Invalid property lookup")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property = self.object
        
        # Check if property is saved by current user
        context['is_saved'] = SavedProperty.objects.filter(
            seeker=self.request.user, 
            property=property
        ).exists()
        
        # Get similar properties (same type, excluding current)
        context['similar_properties'] = Property.objects.filter(
            property_type=property.property_type,
            is_active=True,
            is_published=True
        ).exclude(id=property.id).order_by('?')[:4]  # Random 4 properties
        
        # Add landlord info to context
        context['landlord'] = property.landlord
        
        return context
    
@method_decorator(tenant_required, name='dispatch')
class SavePropertyView(LoginRequiredMixin, TemplateView):
    def get(self, request, *args, **kwargs):
        property = get_object_or_404(Property, id=kwargs.get('property_id'))
        SavedProperty.objects.get_or_create(seeker=request.user, property=property)
        messages.success(request, 'Property saved to your favorites!')
        return redirect(request.META.get('HTTP_REFERER', 'seekers:dashboard'))

@method_decorator(tenant_required, name='dispatch')
class UnsavePropertyView(LoginRequiredMixin, TemplateView):
    def get(self, request, *args, **kwargs):
        property = get_object_or_404(Property, id=kwargs.get('property_id'))
        SavedProperty.objects.filter(seeker=request.user, property=property).delete()
        messages.success(request, 'Property removed from your favorites.')
        return redirect(request.META.get('HTTP_REFERER', 'seekers:dashboard'))

@method_decorator(tenant_required, name='dispatch')
class SavedPropertiesView(LoginRequiredMixin, ListView):
    model = SavedProperty
    template_name = 'seekers/saved_properties.html'
    context_object_name = 'saved_properties'
    paginate_by = 12
    
    def get_queryset(self):
        return SavedProperty.objects.filter(seeker=self.request.user).select_related('property')

@method_decorator(tenant_required, name='dispatch')
class MessageListView(LoginRequiredMixin, ListView):
    template_name = 'seekers/messages/list.html'
    context_object_name = 'conversations'  # Change from 'threads' to 'conversations'
    
    def get_queryset(self):
        # Get conversations where user is a participant
        conversations = Conversation.objects.filter(
            participants=self.request.user
        ).prefetch_related('participants', 'property', 'messages')
        
        conversations_data = []
        for conversation in conversations:
            last_message = conversation.messages.order_by('-created_at').first()
            other_participant = conversation.get_other_participant(self.request.user)
            
            if last_message and other_participant:  # Only include valid conversations
                unread_count = conversation.messages.filter(
                    recipient=self.request.user, 
                    read=False
                ).count()
                
                conversations_data.append({
                    'conversation': conversation,
                    'last_message': last_message,
                    'unread_count': unread_count,
                    'other_participant': other_participant,
                    'property': conversation.property,
                })
        
        return sorted(conversations_data, 
                     key=lambda x: x['last_message'].created_at if x['last_message'] else x['conversation'].created_at, 
                     reverse=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context needed
        return context


@method_decorator(tenant_required, name='dispatch')
class MessageThreadView(LoginRequiredMixin, FormView):
    template_name = 'seekers/messages/thread.html'
    form_class = MessageForm
    
    def get_success_url(self):
        return reverse('seekers:message_thread', kwargs={'user_id': self.kwargs['user_id']})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipient = get_object_or_404(User, id=self.kwargs['user_id'])
        
        # Find the conversation between these users
        conversation = Conversation.objects.filter(
            participants=self.request.user
        ).filter(participants=recipient).filter(conversation_type='direct').first()
        
        if not conversation:
            # Create a new direct conversation
            conversation = Conversation.objects.create(conversation_type='direct')
            conversation.participants.add(self.request.user, recipient)
        
        # Get messages from this conversation
        messages_list = conversation.messages.all().order_by('created_at')
        
        # Mark messages as read
        Message.objects.filter(
            conversation=conversation,
            recipient=self.request.user,
            read=False
        ).update(read=True)
        
        # Decrypt message content for display
        for message in messages_list:
            message.decrypted_content = message.get_decrypted_content()
        
        context['recipient'] = recipient
        context['messages'] = messages_list
        context['conversation'] = conversation
        return context
    
    def form_valid(self, form):
        recipient = get_object_or_404(User, id=self.kwargs['user_id'])
        
        # Find or create conversation
        conversation = Conversation.objects.filter(
            participants=self.request.user
        ).filter(participants=recipient).filter(conversation_type='direct').first()
        
        if not conversation:
            conversation = Conversation.objects.create(conversation_type='direct')
            conversation.participants.add(self.request.user, recipient)
        
        Message.objects.create(
            sender=self.request.user,
            recipient=recipient,
            conversation=conversation,
            content=form.cleaned_data['content'],
            message_type='direct'
        )
        
        messages.success(self.request, 'Message sent!')
        return super().form_valid(form)

@method_decorator(tenant_required, name='dispatch')
class ConversationDetailView(LoginRequiredMixin, View):
    template_name = 'seekers/messages/conversation_detail.html'
    
    def get(self, request, *args, **kwargs):
        try:
            conversation_id = kwargs.get('pk')
            conversation = get_object_or_404(
                Conversation, 
                id=conversation_id, 
                participants=request.user
            )
            
            # Mark messages as read
            Message.objects.filter(
                conversation=conversation,
                recipient=request.user,
                read=False
            ).update(read=True)
            
            # Get messages with decrypted content
            messages_list = conversation.messages.all().order_by('created_at')
            for message in messages_list:
                message.decrypted_content = message.get_decrypted_content()
            
            context = {
                'conversation': conversation,
                'messages': messages_list,
                'other_participant': conversation.get_other_participant(request.user),
                'property': conversation.property,
                'form': MessageForm()  # Add empty form
            }
            
            return render(request, self.template_name, context)
            
        except Exception as e:
            print(f"Error in ConversationDetailView: {e}")
            messages.error(request, 'Error loading conversation')
            return redirect('seekers:messages')
    
    def post(self, request, *args, **kwargs):
        try:
            conversation_id = kwargs.get('pk')
            conversation = get_object_or_404(
                Conversation, 
                id=conversation_id, 
                participants=request.user
            )
            
            content = request.POST.get('content', '').strip()
            reply_to_id = request.POST.get('reply_to')
            
            if not content:
                messages.error(request, 'Message cannot be empty')
                return redirect('seekers:conversation_detail', pk=conversation_id)
            
            recipient = conversation.get_other_participant(request.user)
            if not recipient:
                messages.error(request, 'No recipient found for this conversation')
                return redirect('seekers:messages')
            
            # Handle reply
            reply_to = None
            if reply_to_id:
                try:
                    reply_to = Message.objects.get(id=reply_to_id, conversation=conversation)
                except Message.DoesNotExist:
                    pass
            
            # Create the message
            Message.objects.create(
                sender=request.user,
                recipient=recipient,
                conversation=conversation,
                property=conversation.property,
                content=content,
                reply_to=reply_to,
                message_type=conversation.conversation_type
            )
            
            # Update conversation timestamp
            conversation.updated_at = timezone.now()
            conversation.save()
            
            messages.success(request, 'Message sent!')
            return redirect('seekers:conversation_detail', pk=conversation_id)
            
        except Exception as e:
            print(f"Error sending message: {e}")
            messages.error(request, 'Error sending message')
            return redirect('seekers:messages')


@method_decorator(tenant_required, name='dispatch')
class PropertyMessageView(LoginRequiredMixin, FormView):
    template_name = 'seekers/messages/property_message.html'
    form_class = PropertyMessageForm

    def get_success_url(self):
        return reverse('seekers:conversation_detail', kwargs={'pk': self.conversation.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property_id = self.kwargs['property_id']
        property_obj = get_object_or_404(Property, id=property_id)
        landlord = property_obj.landlord
        
        if not landlord:
            raise Http404("Property does not have a landlord assigned.")

        # Find or create the property conversation
        self.conversation, created = Conversation.objects.get_or_create(
            property=property_obj,
            conversation_type='property',
            defaults={'created_at': timezone.now()}
        )
        
        if created:
            self.conversation.participants.add(landlord, self.request.user)

        # Get messages from this conversation
        messages_list = self.conversation.messages.all().order_by('created_at')
        
        # Decrypt message content for display
        for message in messages_list:
            message.decrypted_content = message.get_decrypted_content()

        context.update({
            'property': property_obj,
            'recipient': landlord,
            'messages': messages_list,
            'conversation': self.conversation,
        })
        return context

    def form_valid(self, form):
        property_obj = get_object_or_404(Property, id=self.kwargs['property_id'])
        landlord = property_obj.landlord
        
        if not landlord:
            raise Http404("Property does not have a landlord assigned.")

        # Get or create conversation
        self.conversation, created = Conversation.objects.get_or_create(
            property=property_obj,
            conversation_type='property',
            defaults={'created_at': timezone.now()}
        )
        
        if created:
            self.conversation.participants.add(landlord, self.request.user)

        # Create the message with property image
        Message.objects.create(
            sender=self.request.user,
            recipient=landlord,
            conversation=self.conversation,
            property=property_obj,
            content=form.cleaned_data['content'],
            message_type='property'
            # property_image will be auto-set in the save() method
        )

        messages.success(self.request, 'Message sent to landlord!')
        return super().form_valid(form)



@method_decorator(tenant_required, name='dispatch')
class CommunityView(LoginRequiredMixin, ListView):
    model = CommunityPost
    template_name = 'seekers/community/list.html'
    context_object_name = 'discussions'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = CommunityPost.objects.all().order_by('-created_at')
        
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
            
        return queryset

@method_decorator(tenant_required, name='dispatch')
class CreatePostView(LoginRequiredMixin, CreateView):
    model = CommunityPost
    form_class = CommunityPostForm
    template_name = 'seekers/community/create.html'
    success_url = reverse_lazy('seekers:community')
    
    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, 'Your discussion has been published!')
        return super().form_valid(form)

@method_decorator(tenant_required, name='dispatch')
class PostDetailView(LoginRequiredMixin, FormView):
    template_name = 'seekers/community/detail.html'
    form_class = CommunityReplyForm
    
    def get_success_url(self):
        return reverse_lazy('seekers:community_detail', kwargs={'pk': self.kwargs['pk']})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = get_object_or_404(
            CommunityPost.objects.prefetch_related('replies__author'), 
            pk=self.kwargs['pk']
        )
        
        # Increment view count - only on GET requests (not form submissions)
        if self.request.method == 'GET':
            CommunityPost.objects.filter(pk=post.pk).update(views=F('views') + 1)
            post.refresh_from_db()
        
        context.update({
            'post': post,
            'replies': post.replies.all().order_by('created_at')
        })
        return context
    
    def form_valid(self, form):
        post = get_object_or_404(CommunityPost, pk=self.kwargs['pk'])
        
        CommunityReply.objects.create(
            post=post,
            author=self.request.user,
            content=form.cleaned_data['content']
        )
        
        messages.success(self.request, 'Your reply has been posted!')
        return super().form_valid(form)

@method_decorator(tenant_required, name='dispatch')
class CommunityReplyView(LoginRequiredMixin, CreateView):
    model = CommunityReply
    form_class = CommunityReplyForm
    template_name = 'seekers/community/reply.html'

    def get_success_url(self):
        return reverse_lazy('seekers:community_detail', kwargs={'pk': self.kwargs['post_id']})

    def form_valid(self, form):
        post = get_object_or_404(CommunityPost, pk=self.kwargs['post_id'])
        reply = form.save(commit=False)
        reply.author = self.request.user
        reply.post = post
        reply.save()
        messages.success(self.request, 'Your reply has been posted!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['post'] = get_object_or_404(CommunityPost, pk=self.kwargs['post_id'])
        return context

@method_decorator(tenant_required, name='dispatch')
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/profile/view.html'
    
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # Prevent caching
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # Force fresh data
        user.refresh_from_db()
        
        # Get or create profile with all related data
        profile = SeekerProfile.objects.select_related('user').get_or_create(user=user)[0]
        profile.refresh_from_db()
        
        context.update({
            'user': user,
            'profile': profile,  # Consistent profile variable
            # 'debug_time': timezone.now(),  # For testing
        })
        return context

@method_decorator(tenant_required, name='dispatch')
class ProfileEditView(LoginRequiredMixin, UpdateView):
    template_name = 'seekers/profile/edit.html'
    form_class = SeekerProfileForm
    success_url = reverse_lazy('seekers:profile')
    
    def get_object(self):
        profile, created = SeekerProfile.objects.get_or_create(user=self.request.user)
        if created:
            profile.phone_number = self.request.user.phone_number
            profile.save()
        return profile
    
    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        initial.update({
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': user.phone_number,
        })
        return initial
    
    def form_valid(self, form):
        # Save the form which will handle the profile picture
        response = super().form_valid(form)
        
        # Update user model
        user = self.request.user
        user.first_name = form.cleaned_data['first_name']
        user.last_name = form.cleaned_data['last_name']
        user.email = form.cleaned_data['email']
        user.phone_number = form.cleaned_data.get('phone_number', '')
        user.save()
        
        messages.success(self.request, 'Profile updated successfully!')
        return response
        
@method_decorator(tenant_required, name='dispatch')
class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'seekers/settings/settings.html'

@method_decorator(tenant_required, name='dispatch')
class ChangePasswordView(LoginRequiredMixin, FormView):
    template_name = 'seekers/settings/change_password.html'
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy('seekers:settings')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)
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
    template_name = 'seekers/settings/deactivate.html'  # Fixed template name
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'deactivate_account'
        return context