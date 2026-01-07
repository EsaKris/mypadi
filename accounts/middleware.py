from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from .models import SecurityLog, User
import logging

logger = logging.getLogger(__name__)

class RoleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        """Extract client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def log_security_event(self, user, action, request):
        """Log security events for audit trail"""
        try:
            SecurityLog.objects.create(
                user=user,
                action=action,
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
            )
        except Exception as e:
            logger.error(f"Failed to log security event: {str(e)}")

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Skip for admin, auth, or public views
        if (request.path.startswith('/admin/') or 
            request.path.startswith('/accounts/') or
            request.path.startswith('/auth/') or
            getattr(view_func, 'public', False)):
            return None

        # Skip for static and media files
        if (request.path.startswith('/static/') or 
            request.path.startswith('/media/') or
            request.path.startswith('/favicon.ico')):
            return None

        # Check if user is authenticated
        if request.user.is_authenticated:
            user = request.user
            
            # Check if account is locked
            if user.is_account_locked():
                self.log_security_event(user, 'ACCESS_DENIED_ACCOUNT_LOCKED', request)
                return render(request, '403.html', {
                    'error_message': 'Your account is temporarily locked due to too many failed login attempts. Please try again later or reset your password.'
                }, status=403)
            
            # Check email verification for protected routes
            if (not user.email_verified and 
                not request.path.startswith('/accounts/verify-email/') and
                not request.path.startswith('/accounts/resend-verification/') and
                not request.path.startswith('/accounts/logout/')):
                
                self.log_security_event(user, 'ACCESS_DENIED_EMAIL_UNVERIFIED', request)
                messages.error(request, "Please verify your email address to access this page.")
                return HttpResponseRedirect(reverse('accounts:resend_verification'))
            
            # Log access to sensitive areas
            if request.path.startswith('/seekers/') or request.path.startswith('/landlords/'):
                self.log_security_event(user, f'ACCESS_{request.path}', request)
        
        # Check tenant access for seekers routes
        if request.path.startswith('/seekers/'):
            if not request.user.is_authenticated:
                self.log_security_event(None, 'ACCESS_DENIED_ANONYMOUS_TENANT_AREA', request)
                return render(request, '403.html', {
                    'error_message': 'Please log in to access tenant features',
                    'login_url': reverse('accounts:login') + f'?next={request.path}'
                }, status=403)
            
            if not request.user.is_tenant():
                self.log_security_event(request.user, 'ACCESS_DENIED_NON_TENANT', request)
                return render(request, '403.html', {
                    'error_message': 'Tenant access required. This area is for property seekers only.',
                    'register_url': reverse('accounts:register') + f'?user_type=tenant&next={request.path}',
                    'required_role': 'tenant',
                    'current_role': 'landlord' if hasattr(request.user, 'is_landlord') and request.user.is_landlord() else 'other'
                }, status=403)
        
        # Check landlord access for landlords routes
        if request.path.startswith('/landlords/'):
            if not request.user.is_authenticated:
                self.log_security_event(None, 'ACCESS_DENIED_ANONYMOUS_LANDLORD_AREA', request)
                return render(request, '403.html', {
                    'error_message': 'Please log in to access landlord features',
                    'login_url': reverse('accounts:login') + f'?next={request.path}'
                }, status=403)
            
            if not request.user.is_landlord():
                self.log_security_event(request.user, 'ACCESS_DENIED_NON_LANDLORD', request)
                return render(request, '403.html', {
                    'error_message': 'Landlord access required. This area is for property owners only.',
                    'register_url': reverse('accounts:register') + f'?user_type=landlord&next={request.path}',
                    'required_role': 'landlord',
                    'current_role': 'tenant' if hasattr(request.user, 'is_tenant') and request.user.is_tenant() else 'other'
                }, status=403)
        
        # Check for mixed role access (users with 'both' role)
        if (request.user.is_authenticated and 
            request.user.user_type == 'both' and
            (request.path.startswith('/seekers/') or request.path.startswith('/landlords/'))):
            
            self.log_security_event(request.user, f'ACCESS_BOTH_ROLES_{request.path}', request)
            return None
            
        return None

    def process_exception(self, request, exception):
        """Handle exceptions in middleware"""
        from django.core.exceptions import PermissionDenied
        from django.http import Http404
        
        if isinstance(exception, (PermissionDenied, Http404)):
            if request.user.is_authenticated:
                self.log_security_event(
                    request.user, 
                    f'EXCEPTION_{exception.__class__.__name__}', 
                    request
                )
        return None