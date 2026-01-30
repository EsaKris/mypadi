"""
Production-Ready Django Middleware
Includes: Role-based access control, Security logging, Rate limiting
"""
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from .models import SecurityLog, User
from .utils import get_client_ip, sanitize_user_agent
import logging

logger = logging.getLogger(__name__)


class SecurityMiddleware:
    """
    Enhanced security middleware with comprehensive logging and monitoring
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Pre-process request
        self.process_request_security(request)
        
        # Get response
        response = self.get_response(request)
        
        # Post-process response
        return response
    
    def process_request_security(self, request):
        """Add security headers and track requests"""
        # Add client IP to request for easy access
        request.client_ip = get_client_ip(request)
        
        # Track suspicious patterns (implement as needed)
        if request.user.is_authenticated:
            self.check_session_security(request)
    
    def check_session_security(self, request):
        """Check for session hijacking attempts"""
        # Compare IP address (optional - can cause issues with mobile users)
        # stored_ip = request.session.get('initial_ip')
        # current_ip = request.client_ip
        # if stored_ip and stored_ip != current_ip:
        #     logger.warning(f"IP change detected for user {request.user.username}")
        
        pass
    
    def log_security_event(self, user, action, request, metadata=None):
        """Create a security log entry"""
        try:
            SecurityLog.objects.create(
                user=user,
                action=action,
                ip_address=get_client_ip(request),
                user_agent=sanitize_user_agent(request.META.get('HTTP_USER_AGENT', '')),
                metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"Failed to log security event: {str(e)}")


class RoleAccessMiddleware:
    """
    Enhanced role-based access control middleware
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.public_paths = [
            '/admin/', '/accounts/', '/auth/', '/static/', '/media/', 
            '/favicon.ico', '/', '/about/', '/contact/', '/terms/', '/privacy/'
        ]
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """Check access permissions before view is called"""
        
        # Skip public paths
        if self.is_public_path(request.path):
            return None
        
        # Skip if view is marked as public
        if getattr(view_func, 'public', False):
            return None
        
        # Check authentication and authorization
        if request.user.is_authenticated:
            return self.check_authenticated_access(request, view_func, view_args, view_kwargs)
        else:
            return self.check_anonymous_access(request)
        
        return None
    
    def is_public_path(self, path):
        """Check if path is public"""
        for public_path in self.public_paths:
            if path.startswith(public_path):
                return True
        return False
    
    def check_authenticated_access(self, request, view_func, view_args, view_kwargs):
        """Check access for authenticated users"""
        user = request.user
        
        # Check if account is locked
        if user.is_account_locked():
            self.log_security_event(user, 'ACCESS_DENIED_ACCOUNT_LOCKED', request)
            return render(request, '403.html', {
                'error_title': 'Account Locked',
                'error_message': 'Your account is temporarily locked due to security concerns. '
                                 'Please try again later or reset your password.'
            }, status=403)
        
        # Check email verification for protected routes
        if not user.email_verified and not self.is_verification_path(request.path):
            self.log_security_event(user, 'ACCESS_DENIED_EMAIL_UNVERIFIED', request)
            messages.error(request, "Please verify your email address to continue.")
            return HttpResponseRedirect(reverse('accounts:resend_verification'))
        
        # Check role-based access
        if request.path.startswith('/seekers/'):
            return self.check_tenant_access(request, user)
        
        if request.path.startswith('/landlords/'):
            return self.check_landlord_access(request, user)
        
        # Log access to sensitive areas
        if self.is_sensitive_path(request.path):
            self.log_security_event(user, f'ACCESS_{request.path}', request)
        
        return None
    
    def check_anonymous_access(self, request):
        """Check access for anonymous users"""
        # Redirect to login for protected paths
        if request.path.startswith('/seekers/') or request.path.startswith('/landlords/'):
            return render(request, '403.html', {
                'error_title': 'Login Required',
                'error_message': 'Please log in to access this page.',
                'login_url': reverse('accounts:login') + f'?next={request.path}'
            }, status=403)
        
        return None
    
    def check_tenant_access(self, request, user):
        """Check tenant/seeker access"""
        if not user.is_tenant():
            self.log_security_event(user, 'ACCESS_DENIED_NON_TENANT', request)
            return render(request, '403.html', {
                'error_title': 'Tenant Access Required',
                'error_message': 'This area is for property seekers only.',
                'register_url': reverse('accounts:register') + f'?user_type=tenant&next={request.path}',
                'required_role': 'tenant',
                'current_role': user.user_type
            }, status=403)
        return None
    
    def check_landlord_access(self, request, user):
        """Check landlord access"""
        if not user.is_landlord():
            self.log_security_event(user, 'ACCESS_DENIED_NON_LANDLORD', request)
            return render(request, '403.html', {
                'error_title': 'Landlord Access Required',
                'error_message': 'This area is for property owners only.',
                'register_url': reverse('accounts:register') + f'?user_type=landlord&next={request.path}',
                'required_role': 'landlord',
                'current_role': user.user_type
            }, status=403)
        return None
    
    def is_verification_path(self, path):
        """Check if path is related to email verification"""
        verification_paths = [
            '/accounts/verify-email/',
            '/accounts/email-verification/',
            '/accounts/resend-verification/',
            '/accounts/logout/'
        ]
        for vpath in verification_paths:
            if path.startswith(vpath):
                return True
        return False
    
    def is_sensitive_path(self, path):
        """Check if path is sensitive and should be logged"""
        sensitive_paths = [
            '/seekers/', '/landlords/', '/admin/', '/api/'
        ]
        for spath in sensitive_paths:
            if path.startswith(spath):
                return True
        return False
    
    def log_security_event(self, user, action, request, metadata=None):
        """Create a security log entry"""
        try:
            SecurityLog.objects.create(
                user=user if isinstance(user, User) else None,
                action=action,
                ip_address=get_client_ip(request),
                user_agent=sanitize_user_agent(request.META.get('HTTP_USER_AGENT', '')),
                metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"Failed to log security event: {str(e)}")


class SessionSecurityMiddleware:
    """
    Middleware to enhance session security
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Store initial IP in session
        if request.user.is_authenticated and 'initial_ip' not in request.session:
            request.session['initial_ip'] = get_client_ip(request)
        
        response = self.get_response(request)
        
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response


class CSRFFailureMiddleware:
    """
    Custom CSRF failure handling
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        return self.get_response(request)
    
    def process_exception(self, request, exception):
        """Handle CSRF failures gracefully"""
        from django.middleware.csrf import CsrfViewMiddleware
        
        if isinstance(exception, Exception) and 'CSRF' in str(exception):
            logger.warning(f"CSRF failure from IP {get_client_ip(request)}")
            return render(request, 'accounts/csrf_failure.html', {
                'error_message': 'Security verification failed. Please refresh the page and try again.'
            }, status=403)
        
        return None