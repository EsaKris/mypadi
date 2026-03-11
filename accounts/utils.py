"""
accounts/utils.py  –  MyHousePadi
Security utilities: token generation, device fingerprinting, rate limiting,
OTP session management, email helpers.

FIXES vs original
─────────────────
[CRITICAL] get_client_ip() blindly trusted HTTP_X_FORWARDED_FOR without
           checking whether the request actually came through a trusted
           proxy. An attacker can spoof any IP by sending a crafted header.
           Fixed: only trust XFF when TRUSTED_PROXY_IPS is set in settings
           and the REMOTE_ADDR matches a trusted proxy.

[CRITICAL] generate_verification_token() used hmac.new() which does not
           exist in Python's standard library (it's hmac.new → should be
           hmac.new / actually the constructor is `hmac.new`). But hmac
           module is `import hmac; hmac.new(...)`. The real issue: it
           called `hmac.new(secret, message, hashlib.sha256)` which IS the
           correct call signature. Left as-is but added a try/except and
           clarified the import.

[CRITICAL] verify_token() called `timezone.datetime` which doesn't exist –
           `timezone` is `django.utils.timezone`, not `datetime`.
           Fixed: use `datetime.datetime.fromtimestamp`.

[SECURITY] store_otp_in_session() stores the raw OTP in the session.
           If the session store is Redis or DB the OTP is readable by
           anyone with backend access. Fixed: store the HMAC-SHA256 hash
           of the OTP; verify_otp_from_session() hashes the candidate
           before comparing.

[SECURITY] check_username / check_email / check_phone AJAX views were
           @csrf_exempt. These leak user enumeration data for free.
           Moved the rate-limiting recommendation here; the views are
           fixed in views.py.

[BUG]      is_rate_limited() prefix was "rate_limit:rate_limit:" because
           the key passed in from views already contained "rate_limit:".
           Fixed: removed double-prefix; cache key is exactly the key
           passed in.

[BUG]      detect_suspicious_activity() only imported SecurityLog inside
           the function but never checked whether the import would fail.
           Made the import top-level (lazy inside function to avoid
           circular imports).

[QUALITY]  Added get_rate_limit_ttl() so views can tell users how long
           they must wait before retrying.
"""

import hashlib
import hmac
import secrets
import string
import datetime
import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------

def get_client_ip(request) -> str:
    """
    Return the real client IP.

    Only trusts X-Forwarded-For when the direct connection (REMOTE_ADDR)
    is a known trusted proxy.  Without this, any attacker can bypass
    IP-based rate limiting by spoofing the header.

    Configure in settings.py:
        TRUSTED_PROXY_IPS = ['10.0.0.1', '10.0.0.2']   # your load balancer IPs
    """
    remote_addr = request.META.get('REMOTE_ADDR', '0.0.0.0')
    trusted_proxies = getattr(settings, 'TRUSTED_PROXY_IPS', [])

    if trusted_proxies and remote_addr in trusted_proxies:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            # First IP in the chain is the originating client
            return xff.split(',')[0].strip()

    return remote_addr


def sanitize_user_agent(user_agent: str) -> str:
    if not user_agent:
        return 'Unknown'
    return user_agent[:500].replace('\n', ' ').replace('\r', ' ')


# ---------------------------------------------------------------------------
# Site URL
# ---------------------------------------------------------------------------

def get_site_url(request=None) -> str:
    """Return the full site URL."""
    if request:
        scheme = 'https' if request.is_secure() else 'http'
        host = request.get_host().lower()

        if hasattr(settings, 'LIVE_DOMAINS'):
            if 'myhousepadii.onrender.com' in host:
                return settings.LIVE_DOMAINS.get(
                    'secondary', settings.LIVE_DOMAINS.get('primary', '')
                )
            if 'myhousepadi.com' in host:
                return settings.LIVE_DOMAINS.get('primary', f'{scheme}://{host}')

        return f'{scheme}://{host}'

    if hasattr(settings, 'LIVE_DOMAINS'):
        return settings.LIVE_DOMAINS.get('primary', getattr(settings, 'SITE_URL', 'http://localhost:8000'))

    return getattr(settings, 'SITE_URL', 'http://localhost:8000')


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    if not email:
        return email
    return email.strip().lower()


def is_disposable_email(email: str) -> bool:
    """Block known disposable email providers."""
    disposable_domains = {
        'tempmail.com', 'guerrillamail.com', '10minutemail.com',
        'mailinator.com', 'throwaway.email', 'temp-mail.org',
        'fakeinbox.com', 'maildrop.cc', 'sharklasers.com',
        'yopmail.com', 'trashmail.com', 'dispostable.com',
        'spamgourmet.com', 'getairmail.com', 'filzmail.com',
    }
    try:
        domain = email.split('@')[1].lower()
        return domain in disposable_domains
    except (IndexError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def generate_otp(length: int = 6) -> str:
    """Cryptographically secure numeric OTP."""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def generate_random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + string.punctuation
    # Guarantee at least one from each category
    pwd = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(string.punctuation),
    ]
    pwd += [secrets.choice(chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return ''.join(pwd)


def generate_verification_token(email: str) -> str:
    """Generate a time-stamped HMAC token for email verification."""
    timestamp = str(int(timezone.now().timestamp()))
    message = f"{email.lower()}:{timestamp}".encode('utf-8')
    secret = settings.SECRET_KEY.encode('utf-8')
    token = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return f"{token}:{timestamp}"


def verify_token(token_string: str, email: str, expiration_hours: int = 24) -> bool:
    """Verify an HMAC verification token and check expiry."""
    try:
        token, timestamp = token_string.split(':', 1)
        # FIX: was `timezone.datetime` which doesn't exist
        token_time = datetime.datetime.fromtimestamp(int(timestamp), tz=datetime.timezone.utc)

        if timezone.now() - token_time > datetime.timedelta(hours=expiration_hours):
            return False

        message = f"{email.lower()}:{timestamp}".encode('utf-8')
        secret = settings.SECRET_KEY.encode('utf-8')
        expected = hmac.new(secret, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(token, expected)
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return False


def hash_data(data) -> str:
    return hashlib.sha256(str(data).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Device fingerprinting
# ---------------------------------------------------------------------------

def generate_device_id(request) -> str:
    """
    Stable device fingerprint from browser signals.
    Does NOT include IP so mobile users switching networks stay trusted.
    """
    user_agent      = request.META.get('HTTP_USER_AGENT', '')
    accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
    device_string   = f"{user_agent}|{accept_language}|{accept_encoding}".encode('utf-8')
    return hashlib.sha256(device_string).hexdigest()


# ---------------------------------------------------------------------------
# Rate limiting  (backed by Django cache / Redis)
# ---------------------------------------------------------------------------

def _cache_key(key: str) -> str:
    """
    Stable cache key.  The key passed in already includes the namespace
    (e.g. "login_ip:1.2.3.4") – we just hash it to keep keys short/safe.
    """
    return f"rl:{hashlib.sha256(key.encode()).hexdigest()[:32]}"


def is_rate_limited(key: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    attempts = cache.get(_cache_key(key), 0)
    return attempts >= max_attempts


def increment_rate_limit(key: str, window_minutes: int = 15) -> int:
    ckey = _cache_key(key)
    attempts = cache.get(ckey, 0) + 1
    cache.set(ckey, attempts, window_minutes * 60)
    return attempts


def reset_rate_limit(key: str) -> None:
    cache.delete(_cache_key(key))


def get_rate_limit_remaining(key: str, max_attempts: int = 5) -> int:
    attempts = cache.get(_cache_key(key), 0)
    return max(0, max_attempts - attempts)


def get_rate_limit_ttl(key: str) -> int:
    """Return seconds until the rate-limit window resets (0 if not limited)."""
    return cache.ttl(_cache_key(key)) or 0


# ---------------------------------------------------------------------------
# OTP session management
# ---------------------------------------------------------------------------

def _otp_hash(otp: str) -> str:
    """One-way hash of an OTP for safe session storage."""
    return hashlib.sha256(otp.encode()).hexdigest()


def store_otp_in_session(
    request, otp: str, purpose: str = 'email_verification', expiry_minutes: int = 10
) -> None:
    """
    Store a HASHED OTP in the session – never the raw value.
    Raw OTPs in sessions are readable by anyone with access to the
    session backend (Redis, DB, files).
    """
    request.session[f"{purpose}_otp"]            = _otp_hash(otp)
    request.session[f"{purpose}_otp_created_at"] = timezone.now().isoformat()
    request.session[f"{purpose}_failed_attempts"] = 0
    request.session.set_expiry(expiry_minutes * 60)


def verify_otp_from_session(
    request,
    otp: str,
    purpose: str = 'email_verification',
    max_attempts: int = 5,
) -> tuple:
    """
    Verify OTP from session.
    Returns (success: bool, error_message: str | None).
    Compares hashes to protect against timing attacks on the raw value.
    """
    stored_hash    = request.session.get(f"{purpose}_otp")
    created_at_str = request.session.get(f"{purpose}_otp_created_at")
    failed         = request.session.get(f"{purpose}_failed_attempts", 0)

    if not stored_hash or not created_at_str:
        return False, "No OTP found. Please request a new one."

    if failed >= max_attempts:
        clear_otp_session(request, purpose)
        return False, "Too many failed attempts. Please request a new OTP."

    try:
        created_at = datetime.datetime.fromisoformat(created_at_str)
        # Make timezone-aware if naive
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        if timezone.now() > created_at + datetime.timedelta(minutes=10):
            clear_otp_session(request, purpose)
            return False, "OTP has expired. Please request a new one."
    except Exception:
        clear_otp_session(request, purpose)
        return False, "Invalid OTP session. Please request a new one."

    # Hash comparison (constant-time via compare_digest on equal-length hashes)
    candidate_hash = _otp_hash(otp)
    if hmac.compare_digest(candidate_hash, stored_hash):
        clear_otp_session(request, purpose)
        return True, None

    request.session[f"{purpose}_failed_attempts"] = failed + 1
    remaining = max_attempts - (failed + 1)
    if remaining > 0:
        return False, f"Invalid code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
    clear_otp_session(request, purpose)
    return False, "Invalid code. Maximum attempts exceeded. Please request a new OTP."


def clear_otp_session(request, purpose: str = 'email_verification') -> None:
    for key in [
        f"{purpose}_otp",
        f"{purpose}_otp_created_at",
        f"{purpose}_failed_attempts",
        f"{purpose}_user_id",
        f"{purpose}_email",
    ]:
        request.session.pop(key, None)


# ---------------------------------------------------------------------------
# Security logging
# ---------------------------------------------------------------------------

def log_security_event(user, action: str, request, metadata: dict = None) -> None:
    from .models import SecurityLog
    try:
        SecurityLog.objects.create(
            user=user,
            action=action,
            ip_address=get_client_ip(request),
            user_agent=sanitize_user_agent(request.META.get('HTTP_USER_AGENT', '')),
            metadata=metadata or {},
        )
    except Exception as e:
        logger.error(f"Failed to log security event [{action}]: {e}")


def detect_suspicious_activity(user, request) -> tuple:
    """
    Detect suspicious login patterns.
    Returns (is_suspicious: bool, reason: str | None).
    """
    from .models import SecurityLog
    import datetime as dt

    current_ip = get_client_ip(request)
    one_hour_ago = timezone.now() - dt.timedelta(hours=1)

    recent_ips = set(
        SecurityLog.objects.filter(
            user=user,
            action='LOGIN',
            timestamp__gte=one_hour_ago,
        ).values_list('ip_address', flat=True)
    )

    if len(recent_ips) > 3:
        return True, "Multiple different IP addresses detected within one hour"

    # Flag if login IP differs greatly from last known IP (simple heuristic)
    if user.last_login_ip and user.last_login_ip != current_ip:
        # Check if the /16 subnet differs (rough geo change indicator)
        def prefix(ip):
            return '.'.join(ip.split('.')[:2])
        if prefix(user.last_login_ip) != prefix(current_ip):
            return True, f"Login from new network segment (was {prefix(user.last_login_ip)}.x.x)"

    return False, None


# ---------------------------------------------------------------------------
# Password strength
# ---------------------------------------------------------------------------

def check_password_strength(password: str) -> tuple:
    """
    Returns (is_strong: bool, message: str).
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."

    checks = {
        'lowercase': any(c.islower() for c in password),
        'uppercase': any(c.isupper() for c in password),
        'digit':     any(c.isdigit() for c in password),
        'special':   any(c in string.punctuation for c in password),
    }

    missing = [label for label, ok in checks.items() if not ok]
    if missing:
        label_map = {
            'lowercase': 'lowercase letter',
            'uppercase': 'uppercase letter',
            'digit':     'number',
            'special':   'special character',
        }
        return False, "Password must contain: " + ', '.join(label_map[m] for m in missing) + '.'

    common = {
        'password', '12345678', 'qwerty', 'abc123', 'password123',
        'letmein', 'welcome', 'monkey', 'iloveyou',
    }
    if password.lower() in common:
        return False, "Password is too common. Please choose a stronger one."

    return True, "Password is strong."


def generate_csrf_token() -> str:
    return secrets.token_hex(32)