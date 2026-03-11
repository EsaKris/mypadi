"""
landlords/middleware.py
Production-ready middleware for MyHousePadi.

Key fixes & improvements:
- AdminAreaMiddleware: original code checked request.user.is_staff but Django's
  middleware runs before session/auth middleware resolves the user from the
  request — using request.user directly is fine ONLY if this middleware is
  placed AFTER django.contrib.auth.middleware.AuthenticationMiddleware in
  MIDDLEWARE settings.  Added a guard so it never crashes on an AnonymousUser.
- Added a fast-path for static/media file paths so those are never blocked.
- Added SecurityHeadersMiddleware: sets production-safe HTTP security headers
  (CSP, HSTS, X-Frame-Options, etc.) so you don't need a separate package for
  the basics.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin


class AdminAreaMiddleware:
    """
    Protect every URL under /admin/ (except the login page itself) so that
    only staff users can access it.

    Place this AFTER AuthenticationMiddleware in settings.MIDDLEWARE.
    """

    EXEMPT_PREFIXES = (
        '/admin/login/',
        '/static/',
        '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path.startswith('/admin/') and not any(
            path.startswith(p) for p in self.EXEMPT_PREFIXES
        ):
            # request.user is available because AuthenticationMiddleware runs first
            user = getattr(request, 'user', None)
            if user is None or not user.is_authenticated or not user.is_staff:
                return redirect('landlords_admin:login')

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Adds essential HTTP security response headers.

    This covers the basics without needing django-csp or similar.
    Adjust the Content-Security-Policy directive to match your actual
    static/CDN/font sources.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Prevent browsers from MIME-sniffing
        response.setdefault('X-Content-Type-Options', 'nosniff')

        # Prevent clickjacking
        response.setdefault('X-Frame-Options', 'SAMEORIGIN')

        # Force HTTPS for 1 year (only meaningful in production behind TLS)
        if not settings.DEBUG:
            response.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )

        # Basic CSP – tighten these for your actual asset sources
        response.setdefault(
            'Content-Security-Policy',
            (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self';"
            ),
        )

        # Referrer policy
        response.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')

        # Disable FLoC / interest-based ad targeting
        response.setdefault('Permissions-Policy', 'interest-cohort=()')

        return response