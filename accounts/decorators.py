"""
Production-Ready Django Decorators
Role-based access control and security decorators
"""
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def tenant_required(view_func):
    """
    Decorator to ensure user is authenticated and has tenant role
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Check authentication
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        
        # Check email verification
        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to access this page.')
            return redirect('accounts:resend_verification')
        
        # Check tenant role
        if not request.user.is_tenant():
            return render(request, '403.html', {
                'error_title': 'Tenant Access Required',
                'error_message': 'This page is for property seekers only.',
                'register_url': reverse('accounts:register') + f'?user_type=tenant&next={request.path}',
                'required_role': 'tenant',
                'current_role': request.user.user_type
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def landlord_required(view_func):
    """
    Decorator to ensure user is authenticated and has landlord role
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Check authentication
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        
        # Check email verification
        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to access this page.')
            return redirect('accounts:resend_verification')
        
        # Check landlord role (including admin)
        if not (request.user.is_landlord() or request.user.is_admin_user()):
            return render(request, '403.html', {
                'error_title': 'Landlord Access Required',
                'error_message': 'This page is for property owners only.',
                'register_url': reverse('accounts:register') + f'?user_type=landlord&next={request.path}',
                'required_role': 'landlord',
                'current_role': request.user.user_type
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def admin_required(view_func):
    """
    Decorator to ensure user is admin or staff
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        
        if not request.user.is_admin_user():
            return render(request, '403.html', {
                'error_title': 'Admin Access Required',
                'error_message': 'This page is for administrators only.',
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def email_verified_required(view_func):
    """
    Decorator to ensure user has verified their email
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        
        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to continue.')
            return redirect('accounts:resend_verification')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def public_view(view_func):
    """
    Mark a view as public (bypass middleware checks)
    """
    view_func.public = True
    return view_func


def rate_limit(max_requests=10, window_minutes=15):
    """
    Decorator for rate limiting views
    Usage: @rate_limit(max_requests=5, window_minutes=10)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            from .utils import is_rate_limited, increment_rate_limit, get_client_ip
            
            # Create rate limit key based on IP or user
            if request.user.is_authenticated:
                key = f"rate_limit:{view_func.__name__}:{request.user.id}"
            else:
                key = f"rate_limit:{view_func.__name__}:{get_client_ip(request)}"
            
            # Check rate limit
            if is_rate_limited(key, max_attempts=max_requests, window_minutes=window_minutes):
                return render(request, '429.html', {
                    'error_message': f'Too many requests. Please try again in {window_minutes} minutes.',
                    'retry_after': window_minutes
                }, status=429)
            
            # Increment counter
            increment_rate_limit(key, window_minutes=window_minutes)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


def account_not_locked(view_func):
    """
    Decorator to check if account is locked
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_account_locked():
            return render(request, '403.html', {
                'error_title': 'Account Locked',
                'error_message': 'Your account is temporarily locked due to security concerns. '
                                 'Please try again later or reset your password.',
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def mfa_exempt(view_func):
    """
    Mark a view as MFA exempt (won't require MFA verification)
    """
    view_func.mfa_exempt = True
    return view_func


def log_view_access(action='VIEW_ACCESS'):
    """
    Decorator to log view access
    Usage: @log_view_access(action='DASHBOARD_ACCESS')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            from .utils import log_security_event
            
            if request.user.is_authenticated:
                log_security_event(
                    request.user, 
                    action, 
                    request,
                    {'view': view_func.__name__}
                )
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


# Combined decorators for common use cases

def tenant_verified(view_func):
    """
    Combined decorator: tenant_required + email_verified_required
    """
    @wraps(view_func)
    @tenant_required
    @email_verified_required
    def _wrapped_view(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def landlord_verified(view_func):
    """
    Combined decorator: landlord_required + email_verified_required
    """
    @wraps(view_func)
    @landlord_required
    @email_verified_required
    def _wrapped_view(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view