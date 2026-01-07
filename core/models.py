from django.db import models
from django.contrib.auth import get_user_model
from cryptography.fernet import Fernet
from django.conf import settings
import base64

User = get_user_model()

class EncryptedMessageMixin:
    def encrypt_content(self, content):
        cipher_suite = Fernet(settings.ENCRYPTION_KEY)
        encrypted_content = cipher_suite.encrypt(content.encode())
        return base64.urlsafe_b64encode(encrypted_content).decode()
    
    def decrypt_content(self, encrypted_content):
        try:
            cipher_suite = Fernet(settings.ENCRYPTION_KEY)
            encrypted_content = base64.urlsafe_b64decode(encrypted_content.encode())
            return cipher_suite.decrypt(encrypted_content).decode()
        except:
            return encrypted_content  # Fallback for unencrypted messages

class Conversation(models.Model):
    CONVERSATION_TYPES = (
        ('direct', 'Direct Chat'),
        ('property', 'Property Inquiry'),
    )
    
    participants = models.ManyToManyField(User, related_name='conversations')
    property = models.ForeignKey('landlords.Property', on_delete=models.CASCADE, null=True, blank=True)
    conversation_type = models.CharField(max_length=20, choices=CONVERSATION_TYPES, default='direct')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-updated_at"]
        unique_together = ['property', 'conversation_type']
    
    def get_last_message(self):
        return self.messages.order_by('-created_at').first()
    
    def get_unread_count(self, user):
        return self.messages.filter(recipient=user, read=False).count()
    
    def get_other_participant(self, user):
        return self.participants.exclude(id=user.id).first()
    
    def __str__(self):
        return f"Conversation {self.id} - {self.conversation_type}"

class Message(EncryptedMessageMixin, models.Model):
    MESSAGE_TYPES = (
        ('direct', 'Direct Message'),
        ('property', 'Property Inquiry'),
    )
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    property = models.ForeignKey('landlords.Property', on_delete=models.CASCADE, null=True, blank=True)
    content = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='direct')
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    property_image = models.ImageField(upload_to='property_chat_images/', null=True, blank=True) 
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def save(self, *args, **kwargs):

     # Auto-set property image if property exists and no image is set
        if self.property and not self.property_image and self.property.images.exists():
            # Set the first property image as the message property image
            self.property_image = self.property.images.first().image

        if self.content and not self.content.startswith('gAAAA'):
            self.content = self.encrypt_content(self.content)
        super().save(*args, **kwargs)
    
    def get_decrypted_content(self):
        return self.decrypt_content(self.content)

    def get_reply_preview(self):
        """Get a short preview of the replied message"""
        if self.reply_to:
            content = self.reply_to.get_decrypted_content()
            return content[:50] + '...' if len(content) > 50 else content
        return None
    
    def __str__(self):
        return f"Message {self.id} from {self.sender} to {self.recipient}"