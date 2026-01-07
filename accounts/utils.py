import hashlib
import hmac
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import secrets
import string


def get_site_url(request=None):
    """
    Return the full site URL based on request host.
    Falls back to primary domain if request is None.
    """
    if request:
        host = request.get_host().lower()
        if 'https://myhousepadii.onrender.com' in host:
            return settings.LIVE_DOMAINS['secondary']
        elif 'myhousepadi.com' in host:
            return settings.LIVE_DOMAINS['primary']
    # Fallback to primary domain
    return settings.LIVE_DOMAINS['primary']


def generate_device_id(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip = request.META.get('REMOTE_ADDR', '')
    device_string = f"{user_agent}{ip}".encode('utf-8')
    return hashlib.sha256(device_string).hexdigest()

def generate_verification_token(email):
    timestamp = str(int(timezone.now().timestamp()))
    message = f"{email}:{timestamp}".encode('utf-8')
    secret = settings.SECRET_KEY.encode('utf-8')
    token = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return f"{token}:{timestamp}"

def verify_token(token_string, email, expiration_hours=24):
    try:
        token, timestamp = token_string.split(':')
        token_time = timezone.datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        
        if timezone.now() - token_time > timedelta(hours=expiration_hours):
            return None
            
        # Recreate the token to verify
        message = f"{email}:{timestamp}".encode('utf-8')
        secret = settings.SECRET_KEY.encode('utf-8')
        expected_token = hmac.new(secret, message, hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(token, expected_token):
            return email
    except (ValueError, IndexError):
        pass
    return None

def generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(characters) for _ in range(length))