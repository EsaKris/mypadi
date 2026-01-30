"""
Production-Ready Security Utilities
Includes: Token generation, device fingerprinting, rate limiting, email utilities
"""
import hashlib
import hmac
import secrets
import string
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def get_site_url(request=None):
    """
    Return the full site URL based on request host.
    Falls back to primary domain if request is None.
    """
    if request:
        host = request.get_host().lower()
        # Check for known domains
        if hasattr(settings, 'LIVE_DOMAINS'):
            if 'https://myhousepadii.onrender.com' in host:
                return settings.LIVE_DOMAINS.get('secondary', settings.LIVE_DOMAINS.get('primary'))
            elif 'myhousepadi.com' in host:
                return settings.LIVE_DOMAINS.get('primary')
        
        # Fallback to building URL from request
        scheme = 'https' if request.is_secure() else 'http'
        return f"{scheme}://{host}"
    
    # Fallback to settings
    if hasattr(settings, 'LIVE_DOMAINS'):
        return settings.LIVE_DOMAINS.get('primary', settings.SITE_URL)
    
    return getattr(settings, 'SITE_URL', 'http://localhost:8000')


def get_client_ip(request):
    """
    Extract client IP address from request with proxy support
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP in the chain
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    return ip


def generate_device_id(request):
    """
    Generate a unique device identifier based on user agent and IP
    More secure than original - uses multiple factors
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip = get_client_ip(request)
    accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
    
    # Combine multiple factors for better uniqueness
    device_string = f"{user_agent}|{ip}|{accept_language}|{accept_encoding}".encode('utf-8')
    return hashlib.sha256(device_string).hexdigest()


def generate_secure_token(length=32):
    """
    Generate a cryptographically secure random token
    """
    return secrets.token_urlsafe(length)


def generate_verification_token(email):
    """
    Generate a secure email verification token with HMAC
    """
    timestamp = str(int(timezone.now().timestamp()))
    message = f"{email.lower()}:{timestamp}".encode('utf-8')
    secret = settings.SECRET_KEY.encode('utf-8')
    token = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return f"{token}:{timestamp}"


def verify_token(token_string, email, expiration_hours=24):
    """
    Verify an HMAC token and check expiration
    """
    try:
        token, timestamp = token_string.split(':')
        token_time = timezone.datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        
        # Check if token is expired
        if timezone.now() - token_time > timedelta(hours=expiration_hours):
            return False
        
        # Recreate the token to verify authenticity
        message = f"{email.lower()}:{timestamp}".encode('utf-8')
        secret = settings.SECRET_KEY.encode('utf-8')
        expected_token = hmac.new(secret, message, hashlib.sha256).hexdigest()
        
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(token, expected_token)
    except (ValueError, IndexError, Exception) as e:
        logger.error(f"Token verification error: {str(e)}")
        return False


def generate_otp(length=6):
    """
    Generate a secure numeric OTP
    """
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def generate_random_password(length=16):
    """
    Generate a secure random password with mixed characters
    """
    # Ensure at least one of each type
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(string.punctuation)
    ]
    
    # Fill the rest
    characters = string.ascii_letters + string.digits + string.punctuation
    password.extend(secrets.choice(characters) for _ in range(length - 4))
    
    # Shuffle the password
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


# Rate Limiting Functions
def is_rate_limited(key, max_attempts=5, window_minutes=15):
    """
    Check if a key (IP, email, etc.) is rate limited using Django cache
    """
    cache_key = f"rate_limit:{key}"
    attempts = cache.get(cache_key, 0)
    return attempts >= max_attempts


def increment_rate_limit(key, window_minutes=15):
    """
    Increment rate limit counter
    """
    cache_key = f"rate_limit:{key}"
    attempts = cache.get(cache_key, 0)
    cache.set(cache_key, attempts + 1, window_minutes * 60)
    return attempts + 1


def reset_rate_limit(key):
    """
    Reset rate limit counter
    """
    cache_key = f"rate_limit:{key}"
    cache.delete(cache_key)


def get_rate_limit_remaining(key, max_attempts=5):
    """
    Get remaining attempts before rate limit
    """
    cache_key = f"rate_limit:{key}"
    attempts = cache.get(cache_key, 0)
    return max(0, max_attempts - attempts)


# OTP Session Management
def store_otp_in_session(request, otp, purpose='email_verification', expiry_minutes=10):
    """
    Securely store OTP in session with metadata
    """
    otp_key = f"{purpose}_otp"
    timestamp_key = f"{purpose}_otp_created_at"
    attempts_key = f"{purpose}_failed_attempts"
    
    request.session[otp_key] = otp
    request.session[timestamp_key] = timezone.now().isoformat()
    request.session[attempts_key] = 0
    request.session.set_expiry(expiry_minutes * 60)


def verify_otp_from_session(request, otp, purpose='email_verification', max_attempts=5):
    """
    Verify OTP from session with rate limiting and expiry check
    Returns: (success: bool, error_message: str or None)
    """
    otp_key = f"{purpose}_otp"
    timestamp_key = f"{purpose}_otp_created_at"
    attempts_key = f"{purpose}_failed_attempts"
    
    stored_otp = request.session.get(otp_key)
    created_at_str = request.session.get(timestamp_key)
    failed_attempts = request.session.get(attempts_key, 0)
    
    # Check if OTP exists
    if not stored_otp or not created_at_str:
        return False, "No OTP found. Please request a new one."
    
    # Check failed attempts
    if failed_attempts >= max_attempts:
        clear_otp_session(request, purpose)
        return False, "Too many failed attempts. Please request a new OTP."
    
    # Check expiry (10 minutes)
    try:
        created_at = timezone.datetime.fromisoformat(created_at_str)
        if timezone.now() > created_at + timedelta(minutes=10):
            clear_otp_session(request, purpose)
            return False, "OTP has expired. Please request a new one."
    except Exception:
        return False, "Invalid OTP session."
    
    # Verify OTP using constant-time comparison
    if secrets.compare_digest(otp, stored_otp):
        clear_otp_session(request, purpose)
        return True, None
    else:
        # Increment failed attempts
        request.session[attempts_key] = failed_attempts + 1
        remaining = max_attempts - (failed_attempts + 1)
        if remaining > 0:
            return False, f"Invalid OTP. {remaining} attempts remaining."
        else:
            clear_otp_session(request, purpose)
            return False, "Invalid OTP. Maximum attempts exceeded."


def clear_otp_session(request, purpose='email_verification'):
    """
    Clear OTP-related session data
    """
    keys = [
        f"{purpose}_otp",
        f"{purpose}_otp_created_at",
        f"{purpose}_failed_attempts",
        f"{purpose}_user_id",
        f"{purpose}_email"
    ]
    for key in keys:
        request.session.pop(key, None)


# Email Utilities
def normalize_email(email):
    """
    Normalize email address (lowercase, strip whitespace)
    """
    if not email:
        return email
    return email.strip().lower()


def is_disposable_email(email):
    """
    Check if email is from a disposable email provider
    Returns True if disposable, False otherwise
    """
    # List of common disposable email domains
    disposable_domains = {
        'tempmail.com', 'guerrillamail.com', '10minutemail.com',
        'mailinator.com', 'throwaway.email', 'temp-mail.org',
        'fakeinbox.com', 'maildrop.cc', 'sharklasers.com'
    }
    
    try:
        domain = email.split('@')[1].lower()
        return domain in disposable_domains
    except (IndexError, AttributeError):
        return False


def hash_data(data):
    """
    Hash data using SHA-256
    """
    return hashlib.sha256(str(data).encode()).hexdigest()


def sanitize_user_agent(user_agent):
    """
    Sanitize user agent string (limit length, remove potential injection)
    """
    if not user_agent:
        return 'Unknown'
    # Limit length and remove potentially dangerous characters
    sanitized = user_agent[:500].replace('\n', ' ').replace('\r', ' ')
    return sanitized


# Security Logging Helpers
def log_security_event(user, action, request, metadata=None):
    """
    Create a security log entry
    """
    from .models import SecurityLog
    
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


def detect_suspicious_activity(user, request):
    """
    Detect suspicious login patterns
    Returns: (is_suspicious: bool, reason: str or None)
    """
    from .models import SecurityLog
    
    current_ip = get_client_ip(request)
    
    # Check for rapid location changes (different IPs in short time)
    recent_logs = SecurityLog.objects.filter(
        user=user,
        action='LOGIN',
        timestamp__gte=timezone.now() - timedelta(hours=1)
    ).values_list('ip_address', flat=True)
    
    if recent_logs.exists():
        unique_ips = set(recent_logs)
        if len(unique_ips) > 3:
            return True, "Multiple IP addresses detected in short period"
    
    # Check for unusual login times (if user has established pattern)
    # This is a placeholder - implement based on your requirements
    
    return False, None


def generate_csrf_token():
    """
    Generate a CSRF-like token for additional security
    """
    return secrets.token_hex(32)


# Password Strength Checker
def check_password_strength(password):
    """
    Check password strength
    Returns: (is_strong: bool, message: str)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    checks = {
        'has_lowercase': any(c.islower() for c in password),
        'has_uppercase': any(c.isupper() for c in password),
        'has_digit': any(c.isdigit() for c in password),
        'has_special': any(c in string.punctuation for c in password),
    }
    
    if not all(checks.values()):
        missing = []
        if not checks['has_lowercase']:
            missing.append('lowercase letter')
        if not checks['has_uppercase']:
            missing.append('uppercase letter')
        if not checks['has_digit']:
            missing.append('number')
        if not checks['has_special']:
            missing.append('special character')
        
        return False, f"Password must contain: {', '.join(missing)}"
    
    # Check for common passwords
    common_passwords = {'password', '12345678', 'qwerty', 'abc123', 'password123'}
    if password.lower() in common_passwords:
        return False, "Password is too common"
    
    return True, "Password is strong"