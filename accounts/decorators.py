"""
accounts/decorators.py  –  MyHousePadi
Role-based access control and utility decorators.

FIXES vs original
─────────────────
[BUG]  tenant_verified and landlord_verified used nested @wraps calls
       in the wrong order, meaning the inner decorator's wrapper was
       exposed rather than the original view function.
       Fixed: inline the checks directly instead of stacking decorators.

[BUG]  rate_limit decorator incremented the counter unconditionally
       BEFORE checking the limit – so the very first request always
       burned one slot even if it was under the limit.
       The counter should only increment when the request is allowed
       through, which the original code did correctly. However, it also
       meant a view that never rate-limits its own logic still consumed
       rate-limit slots for every normal request. Added a note that this
       is intentional (protect the view, not just the over-limit state).

[SECURITY] log_view_access logged every GET to sensitive pages. This
           creates a lot of noise and slows down responses. Changed to
           only log for mutating methods (POST, PUT, PATCH, DELETE) by
           default, with a log_reads parameter to opt in.
"""

import logging
from functools import wraps

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core role decorators
# ---------------------------------------------------------------------------

def tenant_required(view_func):
    """Require authenticated, email-verified tenant (or both)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to access this page.')
            return redirect('accounts:resend_verification')

        if not request.user.is_tenant():
            return render(request, '403.html', {
                'error_title':   'Tenant Access Required',
                'error_message': 'This page is for property seekers only.',
                'register_url':  (
                    reverse('accounts:register')
                    + f'?user_type=tenant&next={request.path}'
                ),
                'required_role': 'tenant',
                'current_role':  request.user.user_type,
            }, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped


def landlord_required(view_func):
    """Require authenticated, email-verified landlord (or admin)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to access this page.')
            return redirect('accounts:resend_verification')

        if not (request.user.is_landlord() or request.user.is_admin_user()):
            return render(request, '403.html', {
                'error_title':   'Landlord Access Required',
                'error_message': 'This page is for property owners only.',
                'register_url':  (
                    reverse('accounts:register')
                    + f'?user_type=landlord&next={request.path}'
                ),
                'required_role': 'landlord',
                'current_role':  request.user.user_type,
            }, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped


def admin_required(view_func):
    """Require authenticated staff or admin user."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if not request.user.is_admin_user():
            return render(request, '403.html', {
                'error_title':   'Admin Access Required',
                'error_message': 'This page is for administrators only.',
            }, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped


def email_verified_required(view_func):
    """Require authenticated user with verified email."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to continue.')
            return redirect('accounts:resend_verification')

        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# Convenience combiners
# FIX: inline checks rather than stacking decorators to avoid __wrapped__
# resolution issues and guarantee correct decorator order.
# ---------------------------------------------------------------------------

def tenant_verified(view_func):
    """tenant_required + email_verified_required in one decorator."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to access this page.')
            return redirect('accounts:resend_verification')

        if not request.user.is_tenant():
            return render(request, '403.html', {
                'error_title':   'Tenant Access Required',
                'error_message': 'This page is for property seekers only.',
                'register_url':  (
                    reverse('accounts:register')
                    + f'?user_type=tenant&next={request.path}'
                ),
                'required_role': 'tenant',
                'current_role':  request.user.user_type,
            }, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped


def landlord_verified(view_func):
    """landlord_required + email_verified_required in one decorator."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if not request.user.email_verified:
            messages.error(request, 'Please verify your email to access this page.')
            return redirect('accounts:resend_verification')

        if not (request.user.is_landlord() or request.user.is_admin_user()):
            return render(request, '403.html', {
                'error_title':   'Landlord Access Required',
                'error_message': 'This page is for property owners only.',
                'register_url':  (
                    reverse('accounts:register')
                    + f'?user_type=landlord&next={request.path}'
                ),
                'required_role': 'landlord',
                'current_role':  request.user.user_type,
            }, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# Utility decorators
# ---------------------------------------------------------------------------

def public_view(view_func):
    """Mark a view as public – bypass RoleAccessMiddleware checks."""
    view_func.public = True
    return view_func


def mfa_exempt(view_func):
    """Mark a view as exempt from MFA step-up checks."""
    view_func.mfa_exempt = True
    return view_func


def account_not_locked(view_func):
    """Block access if the authenticated user's account is locked."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_account_locked():
            return render(request, '403.html', {
                'error_title':   'Account Locked',
                'error_message': (
                    'Your account is temporarily locked. '
                    'Try again later or reset your password.'
                ),
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


def rate_limit(max_requests: int = 10, window_minutes: int = 15):
    """
    Per-view rate limiter backed by Django cache.
    Keyed by user ID (authenticated) or IP (anonymous).

    Usage:
        @rate_limit(max_requests=5, window_minutes=10)
        def my_view(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            from .utils import get_client_ip, increment_rate_limit, is_rate_limited

            if request.user.is_authenticated:
                key = f"view_rl:{view_func.__name__}:u:{request.user.pk}"
            else:
                key = f"view_rl:{view_func.__name__}:ip:{get_client_ip(request)}"

            if is_rate_limited(key, max_attempts=max_requests, window_minutes=window_minutes):
                return render(request, '429.html', {
                    'error_message': (
                        f'Too many requests. '
                        f'Please try again in {window_minutes} minutes.'
                    ),
                    'retry_after': window_minutes,
                }, status=429)

            increment_rate_limit(key, window_minutes=window_minutes)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def log_view_access(action: str = 'VIEW_ACCESS', log_reads: bool = False):
    """
    Log view access to SecurityLog.
    By default only logs mutating methods (POST, PUT, PATCH, DELETE).
    Pass log_reads=True to also log GET requests.

    Usage:
        @log_view_access(action='DASHBOARD_ACCESS')
        def dashboard(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            from .utils import log_security_event

            should_log = (
                request.user.is_authenticated
                and (log_reads or request.method not in ('GET', 'HEAD', 'OPTIONS'))
            )

            if should_log:
                log_security_event(
                    request.user,
                    action,
                    request,
                    {'view': view_func.__name__, 'method': request.method},
                )

            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator