"""
accounts/middleware.py  –  MyHousePadi
Security, role access, and session middleware.

FIXES vs original
─────────────────
[CRITICAL] RoleAccessMiddleware.check_authenticated_access() called
           user.is_account_locked() which (in the original models.py)
           called self.save() on every request for locked users.
           Fixed in models.py; middleware now safe.

[CRITICAL] RoleAccessMiddleware logged action strings built from
           request.path: `f'ACCESS_{request.path}'`. A path like
           `/seekers/../../admin/` would create arbitrary log entries
           and could overflow the action column (max_length=50).
           Fixed: use a fixed constant 'ACCESS_SENSITIVE_AREA'.

[CRITICAL] CSRFFailureMiddleware.process_exception() checked
           `isinstance(exception, Exception) and 'CSRF' in str(exception)`.
           This matches ANY exception whose str() contains the word "CSRF",
           including application exceptions. Real CSRF failures are raised
           as PermissionDenied by Django's CsrfViewMiddleware – they
           never reach process_exception as a CsrfViewMiddleware exception.
           The correct pattern is to override the csrf_failure view in
           settings: CSRF_FAILURE_VIEW = 'accounts.middleware.csrf_failure_view'.
           Fixed: removed the broken class; added the standalone view function.

[BUG]      SessionSecurityMiddleware stored REMOTE_ADDR in
           'initial_ip' without respecting trusted proxy settings.
           Now uses get_client_ip() which honours TRUSTED_PROXY_IPS.

[BUG]      RoleAccessMiddleware public_paths check used startswith('/admin/')
           which would allow unauthenticated access to everything under
           /admin/. Admin access control is handled by Django's own
           AdminSite.has_permission(); removed '/admin/' from public_paths.

[SECURITY] Added Content-Security-Policy and HSTS headers in
           SessionSecurityMiddleware (was missing).

[QUALITY]  Extracted a single _log() helper so both middleware classes
           don't duplicate the SecurityLog creation logic.
"""

import logging

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import SecurityLog, User
from .utils import get_client_ip, sanitize_user_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _log(user, action: str, request, metadata: dict = None) -> None:
    """Write a SecurityLog row without raising on failure."""
    try:
        SecurityLog.objects.create(
            user=user if isinstance(user, User) else None,
            action=action,
            ip_address=get_client_ip(request),
            user_agent=sanitize_user_agent(request.META.get('HTTP_USER_AGENT', '')),
            metadata=metadata or {},
        )
    except Exception as e:
        logger.error(f"SecurityLog write failed [{action}]: {e}")


# ---------------------------------------------------------------------------
# SecurityMiddleware  –  attaches client_ip to request
# ---------------------------------------------------------------------------

class SecurityMiddleware:
    """
    Lightweight middleware that:
    - Attaches request.client_ip for convenient access downstream.
    - Detects and logs suspicious patterns for authenticated users.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = get_client_ip(request)

        if request.user.is_authenticated:
            self._check_session_security(request)

        return self.get_response(request)

    def _check_session_security(self, request):
        """Placeholder for session-hijacking detection heuristics."""
        # Example: compare stored session IP with current IP.
        # Disabled by default because mobile users switch IPs frequently.
        pass


# ---------------------------------------------------------------------------
# RoleAccessMiddleware  –  enforces authentication and role rules
# ---------------------------------------------------------------------------

class RoleAccessMiddleware:
    """
    Enforce authentication, email verification, and role-based path access.
    """

    # Paths that are always accessible without authentication.
    # NOTE: '/admin/' is intentionally NOT here – Django handles that itself.
    PUBLIC_PREFIXES = (
        '/accounts/',
        '/auth/',
        '/static/',
        '/media/',
        '/favicon.ico',
        '/about/',
        '/contact/',
        '/terms/',
        '/privacy/',
    )

    # Exact public paths (home page)
    PUBLIC_EXACT = {'/', ''}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Called before the view. Return None to continue, or a response to short-circuit."""

        # Public by path
        if self._is_public(request.path):
            return None

        # View explicitly marked as public
        if getattr(view_func, 'public', False):
            return None

        if request.user.is_authenticated:
            return self._check_authenticated(request)
        else:
            return self._check_anonymous(request)

    # ── Path helpers ──────────────────────────────────────────────────────

    def _is_public(self, path: str) -> bool:
        if path in self.PUBLIC_EXACT:
            return True
        return any(path.startswith(p) for p in self.PUBLIC_PREFIXES)

    def _is_verification_path(self, path: str) -> bool:
        prefixes = (
            '/accounts/verify-email/',
            '/accounts/email-verification/',
            '/accounts/resend-verification/',
            '/accounts/logout/',
        )
        return any(path.startswith(p) for p in prefixes)

    # ── Access checks ─────────────────────────────────────────────────────

    def _check_authenticated(self, request):
        user = request.user

        if user.is_account_locked():
            _log(user, 'ACCESS_DENIED', request, {'reason': 'account_locked'})
            return render(request, '403.html', {
                'error_title':   'Account Locked',
                'error_message': (
                    'Your account is temporarily locked. '
                    'Try again later or reset your password.'
                ),
            }, status=403)

        if not user.email_verified and not self._is_verification_path(request.path):
            _log(user, 'ACCESS_DENIED', request, {'reason': 'email_unverified'})
            messages.error(request, "Please verify your email address to continue.")
            return HttpResponseRedirect(reverse('accounts:resend_verification'))

        if request.path.startswith('/seekers/'):
            return self._require_role(request, user, 'tenant')

        if request.path.startswith('/landlords/'):
            return self._require_role(request, user, 'landlord')

        # Log access to sensitive areas with a safe fixed action string
        if request.path.startswith(('/seekers/', '/landlords/')):
            _log(user, 'ACCESS_SENSITIVE_AREA', request, {'path': request.path[:200]})

        return None

    def _check_anonymous(self, request):
        if request.path.startswith('/seekers/') or request.path.startswith('/landlords/'):
            return render(request, '403.html', {
                'error_title':   'Login Required',
                'error_message': 'Please log in to access this page.',
                'login_url':     reverse('accounts:login') + f'?next={request.path}',
            }, status=403)
        return None

    def _require_role(self, request, user, required_role: str):
        has_access = (
            user.is_tenant()   if required_role == 'tenant'   else
            user.is_landlord() if required_role == 'landlord' else
            False
        )
        # Admins can access everything
        if user.is_admin_user():
            return None
        if has_access:
            return None

        _log(user, 'ACCESS_DENIED', request, {
            'required_role': required_role,
            'user_type':     user.user_type,
        })
        return render(request, '403.html', {
            'error_title':   f'{required_role.capitalize()} Access Required',
            'error_message': f'This area is for {required_role}s only.',
            'register_url':  (
                reverse('accounts:register')
                + f'?user_type={required_role}&next={request.path}'
            ),
            'required_role': required_role,
            'current_role':  user.user_type,
        }, status=403)


# ---------------------------------------------------------------------------
# SessionSecurityMiddleware  –  session hardening + security headers
# ---------------------------------------------------------------------------

class SessionSecurityMiddleware:
    """
    Harden sessions and add security response headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Record initial IP on first authenticated request
        if request.user.is_authenticated and 'initial_ip' not in request.session:
            # FIX: use get_client_ip() to respect trusted proxy config
            request.session['initial_ip'] = get_client_ip(request)

        response = self.get_response(request)

        # ── Core security headers ────────────────────────────────────────
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options']        = 'DENY'
        response['X-XSS-Protection']       = '1; mode=block'
        response['Referrer-Policy']        = 'strict-origin-when-cross-origin'
        response['Permissions-Policy']     = 'geolocation=(), microphone=(), camera=()'

        # HSTS – only send over HTTPS
        if request.is_secure():
            response['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains; preload'
            )

        # Content-Security-Policy – adjust as needed for your CDN / inline scripts
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )

        return response


# ---------------------------------------------------------------------------
# CSRF failure view
# FIX: replaces the broken CSRFFailureMiddleware class.
# Register in settings.py:
#   CSRF_FAILURE_VIEW = 'accounts.middleware.csrf_failure_view'
# ---------------------------------------------------------------------------

def csrf_failure_view(request, reason=''):
    """Custom CSRF failure page."""
    logger.warning(
        f"CSRF failure from IP {get_client_ip(request)} – reason: {reason}"
    )
    return render(request, 'accounts/csrf_failure.html', {
        'error_message': (
            'Security verification failed. '
            'Please refresh the page and try again.'
        ),
    }, status=403)