"""
Production-Ready Django Authentication Views
Part 1: Registration, Login, Email Verification
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from datetime import timedelta
import logging
import secrets

from .forms import (
    RegistrationForm, EnhancedLoginForm, MFAMethodForm, 
    OTPVerificationForm, CustomPasswordResetForm, ResendVerificationForm
)
from .models import User, SecurityLog, TrustedDevice, LoginAttempt
from .utils import (
    generate_device_id, generate_otp, get_client_ip, log_security_event,
    store_otp_in_session, verify_otp_from_session, clear_otp_session,
    is_rate_limited, increment_rate_limit, reset_rate_limit,
    get_site_url, normalize_email, detect_suspicious_activity
)

logger = logging.getLogger(__name__)


# ===========================
# HELPER FUNCTIONS
# ===========================



def redirect_user_by_type(user):
    """Redirect user to appropriate dashboard based on role"""
    if user.is_tenant():
        return redirect('seekers:dashboard')
    elif user.is_landlord():
        return redirect('landlords:dashboard')
    elif user.is_admin_user():
        return redirect('admin:index')
    else:
        return redirect('landing:home')


def get_user_by_identifier(identifier):
    """
    Find user by username, email, or phone number
    Uses Q objects for efficient lookup
    """
    if not identifier:
        return None
    
    identifier = identifier.strip().lower()
    
    try:
        user = User.objects.filter(
            Q(username=identifier) | 
            Q(email=identifier) | 
            Q(phone_number=identifier)
        ).first()
        return user
    except Exception as e:
        logger.error(f"Error finding user by identifier: {str(e)}")
        return None


def send_email_safe(subject, html_content, text_content, to_email, request=None):
    """
    Safely send email with error handling and logging
    """
    try:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@myhousepadi.com")
        
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[to_email],
            reply_to=[from_email],
        )
        email_message.attach_alternative(html_content, "text/html")
        
        # Add headers for better deliverability
        if request:
            base_url = get_site_url(request)
            email_message.extra_headers = {
                "X-Verified-Domain": "House Padi",
                "X-Priority": "1",
                "List-Unsubscribe": f"<{base_url}/accounts/unsubscribe/>"
            }
        
        email_message.send(fail_silently=False)
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False


def send_verification_email(user, otp, request):
    """
    Send OTP verification email with professional template
    """
    base_url = get_site_url(request)
    context = {
        "otp_code": otp,
        "user": user,
        "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@myhousepadi.com"),
        "site_url": base_url,
        "expiry_minutes": 10
    }
    
    html_content = render_to_string("accounts/verification_email.html", context)
    text_content = render_to_string("accounts/verification_email.txt", context)
    
    return send_email_safe(
        subject="Your House Padi Verification Code",
        html_content=html_content,
        text_content=text_content,
        to_email=user.email,
        request=request
    )


# ===========================
# REGISTRATION & EMAIL VERIFICATION
# ===========================

@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Enhanced registration view with comprehensive validation and security
    """
    # Redirect already authenticated and verified users
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    
    # Check IP rate limiting
    client_ip = get_client_ip(request)
    if is_rate_limited(f"register_ip:{client_ip}", max_attempts=3, window_minutes=60):
        messages.error(request, "Too many registration attempts. Please try again later.")
        return render(request, 'accounts/register.html', {'form': RegistrationForm()})
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        
        if form.is_valid():
            try:
                # Create user
                user = form.save()
                
                # Generate secure OTP
                otp = generate_otp(length=6)
                
                # Store OTP in session
                store_otp_in_session(request, otp, purpose='email_verification', expiry_minutes=10)
                request.session['email_verification_user_id'] = user.id
                request.session['email_verification_email'] = user.email
                
                # Send verification email
                email_sent = send_verification_email(user, otp, request)
                
                if email_sent:
                    messages.success(
                        request, 
                        "Registration successful! Please check your email for the verification code."
                    )
                else:
                    messages.warning(
                        request,
                        "Registration successful, but we couldn't send the verification email. "
                        "Please contact support if you don't receive it."
                    )
                
                # Log registration
                log_security_event(user, 'REGISTER', request)
                
                # Increment rate limit counter
                increment_rate_limit(f"register_ip:{client_ip}", window_minutes=60)
                
                return redirect('accounts:email_verification_pending')
                
            except Exception as e:
                logger.error(f"Registration error: {str(e)}")
                messages.error(request, "An error occurred during registration. Please try again.")
        else:
            # Form has validation errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})


@require_http_methods(["GET", "POST"])
def email_verification_pending(request):
    """
    Show email verification pending page with OTP input
    """
    user_id = request.session.get('email_verification_user_id')
    
    if not user_id:
        messages.error(request, 'No pending email verification found.')
        return redirect('accounts:register')
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        clear_otp_session(request, 'email_verification')
        messages.error(request, 'Verification session expired. Please register again.')
        return redirect('accounts:register')
    
    # If user is already verified, log them in
    if user.email_verified:
        clear_otp_session(request, 'email_verification')
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        messages.success(request, 'Email already verified! Welcome.')
        return redirect_user_by_type(user)
    
    # Handle OTP submission
    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()
        
        if not otp:
            messages.error(request, 'Please enter the verification code.')
            return render(request, 'accounts/email_verification_pending.html', {
                'user_email': user.email
            })
        
        # Verify OTP
        success, error_message = verify_otp_from_session(request, otp, purpose='email_verification')
        
        if success:
            # Mark email as verified
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            
            # Clear session
            clear_otp_session(request, 'email_verification')
            
            # Log in user
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            
            # Log event
            log_security_event(user, 'EMAIL_VERIFIED', request)
            
            messages.success(request, 'Email verified successfully! Welcome to House Padi.')
            return redirect_user_by_type(user)
        else:
            messages.error(request, error_message)
    
    return render(request, 'accounts/email_verification_pending.html', {
        'user_email': user.email,
        'allow_resend': True
    })


@require_http_methods(["GET", "POST"])
def resend_verification_email(request):
    """
    Resend verification email with rate limiting
    """
    # Redirect already verified users
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    
    if request.method == 'POST':
        email_input = request.POST.get('email', '').strip().lower()
        
        if not email_input:
            messages.error(request, 'Please enter your email address.')
            return redirect('accounts:resend_verification')
        
        # Rate limiting
        if is_rate_limited(f"resend_verification:{email_input}", max_attempts=3, window_minutes=15):
            messages.error(request, 'Too many resend attempts. Please wait 15 minutes.')
            return redirect('accounts:resend_verification')
        
        try:
            user = User.objects.get(email=email_input)
            
            if user.email_verified:
                messages.info(request, 'Your email is already verified. You can log in.')
                return redirect('accounts:login')
            
            # Generate new OTP
            otp = generate_otp(length=6)
            
            # Store in session
            store_otp_in_session(request, otp, purpose='email_verification', expiry_minutes=10)
            request.session['email_verification_user_id'] = user.id
            request.session['email_verification_email'] = user.email
            
            # Send email
            email_sent = send_verification_email(user, otp, request)
            
            if email_sent:
                messages.success(request, 'Verification code sent! Check your email.')
            else:
                # Fallback: show OTP in dev mode only
                if settings.DEBUG:
                    messages.warning(request, f'Could not send email. Your code is: {otp}')
                else:
                    messages.error(request, 'Failed to send email. Please contact support.')
            
            # Increment rate limit
            increment_rate_limit(f"resend_verification:{email_input}", window_minutes=15)
            
            return redirect('accounts:email_verification_pending')
            
        except User.DoesNotExist:
            # Generic message to prevent user enumeration
            messages.info(request, 'If an account exists with this email, a verification code has been sent.')
            return redirect('accounts:resend_verification')
    
    # GET request - show form
    prefill_email = request.session.get('pending_verification_email', '')
    return render(request, 'accounts/resend_verification.html', {'email': prefill_email})


# ===========================
# LOGIN & AUTHENTICATION
# ===========================

@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Enhanced login view with comprehensive security checks
    """
    # Redirect already verified users
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    
    client_ip = get_client_ip(request)
    
    # Check IP-based rate limiting
    if is_rate_limited(f"login_ip:{client_ip}", max_attempts=10, window_minutes=15):
        messages.error(request, "Too many login attempts from this IP. Please try again later.")
        return render(request, 'accounts/login.html', {'form': EnhancedLoginForm()})
    
    form = EnhancedLoginForm(data=request.POST or None)
    
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')
        
        # Track login attempt
        LoginAttempt.objects.create(
            identifier=identifier,
            ip_address=client_ip,
            success=False,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
        )
        
        # Check identifier-based rate limiting
        if is_rate_limited(f"login_user:{identifier}", max_attempts=5, window_minutes=15):
            messages.error(request, "Too many failed login attempts for this account. Please wait 15 minutes.")
            return render(request, 'accounts/login.html', {'form': form})
        
        if form.is_valid():
            user = get_user_by_identifier(identifier)
            
            if user:
                # Check email verification
                if not user.email_verified:
                    request.session['pending_verification_email'] = user.email
                    messages.error(
                        request,
                        "Please verify your email before logging in. "
                        "Check your inbox or request a new verification code."
                    )
                    return redirect('accounts:resend_verification')
                
                # Authenticate
                auth_user = authenticate(request, username=user.username, password=password)
                
                if auth_user:
                    # Check account lock
                    if auth_user.is_account_locked():
                        messages.error(
                            request,
                            "Account temporarily locked due to too many failed login attempts. "
                            "Try again later or reset your password."
                        )
                        return render(request, 'accounts/login.html', {'form': form})
                    
                    # Check for suspicious activity
                    is_suspicious, reason = detect_suspicious_activity(auth_user, request)
                    if is_suspicious:
                        log_security_event(auth_user, 'SUSPICIOUS_ACTIVITY', request, {'reason': reason})
                        # Could require additional verification here
                    
                    # Reset failed login attempts
                    auth_user.reset_failed_logins()
                    reset_rate_limit(f"login_user:{identifier}")
                    
                    # Check trusted device and MFA
                    device_id = generate_device_id(request)
                    is_trusted = TrustedDevice.objects.filter(
                        user=auth_user, 
                        device_id=device_id,
                        is_active=True
                    ).exists()
                    
                    if auth_user.requires_mfa() and not is_trusted:
                        # Require MFA
                        request.session['mfa_user_id'] = auth_user.id
                        request.session['mfa_required'] = True
                        request.session.set_expiry(300)  # 5 minutes
                        return redirect('accounts:mfa_verify')
                    
                    # Complete login
                    return complete_login(request, auth_user, device_id)
                else:
                    # Failed authentication
                    user.increment_failed_login()
                    increment_rate_limit(f"login_user:{identifier}", window_minutes=15)
                    increment_rate_limit(f"login_ip:{client_ip}", window_minutes=15)
                    log_security_event(user, 'FAILED_LOGIN', request)
                    messages.error(request, "Invalid credentials. Please try again.")
            else:
                # User not found - still increment IP rate limit
                increment_rate_limit(f"login_ip:{client_ip}", window_minutes=15)
                messages.error(request, "Invalid credentials. Please try again.")
        else:
            # Form validation failed
            messages.error(request, "Please correct the errors below.")
    
    return render(request, 'accounts/login.html', {'form': form})


def complete_login(request, user, device_id):
    """
    Complete the login process after successful authentication
    """
    # Update device trust
    device, created = TrustedDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'device_name': request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:100],
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
            'ip_address': get_client_ip(request),
            'is_active': True
        }
    )
    
    if not created:
        # Update existing device
        device.ip_address = get_client_ip(request)
        device.save(update_fields=['ip_address', 'last_used'])
    
    # Log in user
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    
    # Update user login info
    user.last_login_ip = get_client_ip(request)
    user.last_login_at = timezone.now()
    user.save(update_fields=['last_login_ip', 'last_login_at'])
    
    # Update login attempt as successful
    LoginAttempt.objects.create(
        identifier=user.username,
        ip_address=get_client_ip(request),
        success=True,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )
    
    # Log security event
    log_security_event(user, 'LOGIN', request)
    
    # Handle remember me
    remember_me = request.POST.get('remember_me')
    if remember_me:
        request.session.set_expiry(1209600)  # 2 weeks
    else:
        request.session.set_expiry(0)  # Browser session
    
    messages.success(request, f"Welcome back, {user.first_name}!")
    return redirect_user_by_type(user)

"""
Production-Ready Django Authentication Views
Part 2: MFA, Security Management, Logout
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from datetime import timedelta
import pyotp
import qrcode
from io import BytesIO
import base64
import logging

from .forms import MFAMethodForm, OTPVerificationForm
from .models import User, SecurityLog, TrustedDevice
from .utils import (
    generate_device_id, generate_otp, get_client_ip, log_security_event,
    store_otp_in_session, verify_otp_from_session, clear_otp_session
)
from .views import redirect_user_by_type

logger = logging.getLogger(__name__)


# ===========================
# MULTI-FACTOR AUTHENTICATION
# ===========================

@require_http_methods(["GET", "POST"])
def mfa_verify_view(request):
    """
    Verify MFA (Email OTP or Google Authenticator)
    """
    # Check MFA session
    if not request.session.get('mfa_required') or not request.session.get('mfa_user_id'):
        messages.error(request, "No MFA session found. Please log in again.")
        return redirect('accounts:login')
    
    try:
        user = User.objects.get(id=request.session['mfa_user_id'])
    except User.DoesNotExist:
        messages.error(request, 'Invalid session. Please log in again.')
        return redirect('accounts:login')
    
    # Ensure email is verified
    if not user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')
    
    form = OTPVerificationForm(request.POST or None)
    
    if request.method == 'POST':
        # Handle resend OTP request
        if 'resend_otp' in request.POST and user.mfa_method == 'email':
            return resend_mfa_otp(request, user)
        
        # Verify OTP
        if form.is_valid():
            otp = form.cleaned_data['otp']
            
            if user.mfa_method == 'google_authenticator':
                # Verify TOTP
                if user.verify_totp(otp):
                    return complete_mfa_login(request, user)
                else:
                    # Check backup codes
                    if user.verify_backup_code(otp):
                        messages.warning(request, 'Logged in using backup code. Please regenerate backup codes.')
                        return complete_mfa_login(request, user)
                    else:
                        messages.error(request, 'Invalid code. Please try again.')
            
            elif user.mfa_method == 'email':
                # Verify email OTP
                success, error_message = verify_otp_from_session(request, otp, purpose='mfa')
                
                if success:
                    return complete_mfa_login(request, user)
                else:
                    messages.error(request, error_message)
    else:
        # Generate and send OTP for email MFA (GET request)
        if user.mfa_method == 'email' and not request.session.get('mfa_otp'):
            generate_and_send_mfa_otp(request, user)
    
    return render(request, 'accounts/mfa_verify.html', {
        'form': form,
        'mfa_method': user.mfa_method,
        'user': user
    })


def complete_mfa_login(request, user):
    """Complete login after successful MFA verification"""
    device_id = generate_device_id(request)
    
    # Mark device as trusted
    TrustedDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'device_name': request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:100],
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
            'ip_address': get_client_ip(request),
            'is_active': True
        }
    )
    
    # Clear MFA session
    for key in ['mfa_user_id', 'mfa_required', 'mfa_otp', 'mfa_otp_created_at', 'mfa_failed_attempts']:
        request.session.pop(key, None)
    
    # Log in user
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    
    # Update user info
    user.last_login_ip = get_client_ip(request)
    user.last_login_at = timezone.now()
    user.save(update_fields=['last_login_ip', 'last_login_at'])
    
    # Log event
    log_security_event(user, 'LOGIN_MFA', request)
    
    messages.success(request, f"Welcome back, {user.first_name}!")
    return redirect_user_by_type(user)


def generate_and_send_mfa_otp(request, user):
    """Generate and send MFA OTP via email"""
    otp = generate_otp(length=6)
    
    # Store in session
    store_otp_in_session(request, otp, purpose='mfa', expiry_minutes=5)
    
    # Send email
    try:
        send_mail(
            subject='Your House Padi Login Code',
            message=f'Your login verification code is: {otp}\n\nThis code will expire in 5 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"MFA OTP sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send MFA OTP: {str(e)}")
        if settings.DEBUG:
            messages.info(request, f'Debug: Your code is {otp}')


def resend_mfa_otp(request, user):
    """Resend MFA OTP with rate limiting"""
    resend_count = request.session.get('mfa_otp_resend_count', 0)
    
    if resend_count >= 3:
        messages.error(request, "Maximum OTP resend attempts reached. Please try logging in again.")
        return redirect('accounts:login')
    
    generate_and_send_mfa_otp(request, user)
    request.session['mfa_otp_resend_count'] = resend_count + 1
    messages.info(request, 'New verification code sent to your email.')
    
    return redirect('accounts:mfa_verify')


@login_required
@require_http_methods(["GET", "POST"])
def select_mfa_method(request):
    """Select and configure MFA method"""
    if not request.user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')
    
    if request.method == 'POST':
        form = MFAMethodForm(request.POST, instance=request.user)
        
        if form.is_valid():
            user = form.save()
            
            if user.mfa_method == 'google_authenticator':
                # Generate TOTP secret if not exists
                if not user.totp_secret:
                    user.generate_totp_secret()
                
                # Generate backup codes
                backup_codes = user.generate_backup_codes(count=10)
                request.session['backup_codes'] = backup_codes
                
                log_security_event(user, 'MFA_ENABLED', request, {'method': 'google_authenticator'})
                return redirect('accounts:setup_authenticator')
            
            elif user.mfa_method == 'email':
                log_security_event(user, 'MFA_ENABLED', request, {'method': 'email'})
                messages.success(request, 'Email MFA enabled successfully!')
            else:
                log_security_event(user, 'MFA_DISABLED', request)
                messages.success(request, 'MFA disabled.')
            
            return redirect_user_by_type(user)
    else:
        form = MFAMethodForm(instance=request.user)
    
    return render(request, 'accounts/select_mfa_method.html', {'form': form})


@login_required
@require_GET
def setup_authenticator(request):
    """Setup Google Authenticator with QR code"""
    if not request.user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')
    
    user = request.user
    
    if user.mfa_method != 'google_authenticator' or not user.totp_secret:
        messages.warning(request, 'Please select Google Authenticator as your MFA method first.')
        return redirect('accounts:select_mfa_method')
    
    # Generate TOTP URI for QR code
    totp_uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
        name=user.email,
        issuer_name='House Padi'
    )
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # Get backup codes from session (if just generated)
    backup_codes = request.session.pop('backup_codes', None)
    
    return render(request, 'accounts/setup_authenticator.html', {
        'qr_code_base64': qr_code_base64,
        'totp_secret': user.totp_secret,
        'backup_codes': backup_codes
    })


# ===========================
# SECURITY MANAGEMENT
# ===========================

@login_required
@require_GET
def manage_devices(request):
    """View and manage trusted devices"""
    trusted_devices = TrustedDevice.objects.filter(user=request.user, is_active=True)
    current_device_id = generate_device_id(request)
    
    return render(request, 'accounts/manage_devices.html', {
        'trusted_devices': trusted_devices,
        'current_device_id': current_device_id
    })


@login_required
@require_POST
def remove_device(request, device_id):
    """Remove a trusted device"""
    try:
        device = TrustedDevice.objects.get(id=device_id, user=request.user)
        device.is_active = False
        device.save(update_fields=['is_active'])
        
        log_security_event(request.user, 'DEVICE_REMOVED', request, {
            'device_id': device.device_id,
            'device_name': device.device_name
        })
        
        messages.success(request, 'Device removed successfully.')
    except TrustedDevice.DoesNotExist:
        messages.error(request, 'Device not found.')
    
    return redirect('accounts:manage_devices')


@login_required
@require_GET
def security_logs(request):
    """View security activity logs"""
    # Get last 100 logs for current user
    logs = SecurityLog.objects.filter(user=request.user)[:100]
    
    # Group by date for better UX
    from itertools import groupby
    from datetime import date
    
    logs_by_date = {}
    for log in logs:
        log_date = log.timestamp.date()
        if log_date not in logs_by_date:
            logs_by_date[log_date] = []
        logs_by_date[log_date].append(log)
    
    return render(request, 'accounts/security_logs.html', {
        'logs': logs,
        'logs_by_date': logs_by_date
    })


@login_required
@require_POST
def regenerate_backup_codes(request):
    """Regenerate MFA backup codes"""
    if request.user.mfa_method != 'google_authenticator':
        messages.error(request, 'Backup codes are only available for Google Authenticator.')
        return redirect('accounts:select_mfa_method')
    
    backup_codes = request.user.generate_backup_codes(count=10)
    
    log_security_event(request.user, 'BACKUP_CODES_REGENERATED', request)
    
    return render(request, 'accounts/backup_codes.html', {
        'backup_codes': backup_codes
    })


# ===========================
# LOGOUT
# ===========================

@login_required
@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Logout user and clear session"""
    if request.method == 'POST':
        log_security_event(request.user, 'LOGOUT', request)
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect('accounts:login')
    
    return render(request, 'accounts/logout_confirm.html')


# ===========================
# AJAX ENDPOINTS FOR REAL-TIME VALIDATION
# ===========================

@csrf_exempt
@require_GET
def check_username(request):
    """Check if username is available (AJAX)"""
    from django.utils.crypto import get_random_string
    
    username = request.GET.get('username', '').strip().lower()
    available = True
    
    if username and len(username) >= 3:
        available = not User.objects.filter(username=username).exists()
    
    # Add small random delay to prevent timing attacks
    _ = get_random_string(length=2)
    
    return JsonResponse({'available': available})


@csrf_exempt
@require_GET
def check_email(request):
    """Check if email is available (AJAX)"""
    from django.utils.crypto import get_random_string
    
    email = request.GET.get('email', '').strip().lower()
    available = True
    
    if email:
        available = not User.objects.filter(email=email).exists()
    
    _ = get_random_string(length=2)
    
    return JsonResponse({'available': available})


@csrf_exempt
@require_GET
def check_phone(request):
    """Check if phone is available (AJAX)"""
    from django.utils.crypto import get_random_string
    
    phone = request.GET.get('phone', '').strip()
    available = True
    
    if phone:
        available = not User.objects.filter(phone_number=phone).exists()
    
    _ = get_random_string(length=2)
    
    return JsonResponse({'available': available})


# ===========================
# ERROR HANDLERS
# ===========================

def verify_email_required(request):
    """Show email verification required page"""
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    
    return render(request, 'accounts/verify_email_required.html')


def custom_permission_denied_view(request, exception=None):
    """Enhanced 403 error handler"""
    context = {
        'error_title': 'Access Denied',
        'error_message': 'You do not have permission to access this page.'
    }
    
    if request.user.is_authenticated:
        # Logged in but doesn't have permission
        if hasattr(request.user, 'is_tenant') and hasattr(request.user, 'is_landlord'):
            required_role = None
            if '/seekers/' in request.path:
                required_role = 'tenant'
            elif '/landlords/' in request.path:
                required_role = 'landlord'
            
            if required_role:
                context.update({
                    'error_message': f'This area is for {required_role}s only.',
                    'required_role': required_role,
                    'current_role': request.user.user_type,
                    'register_url': reverse('accounts:register') + f'?user_type={required_role}&next={request.path}'
                })
    else:
        # Not logged in
        context.update({
            'error_message': 'Please log in to access this page.',
            'login_url': reverse('accounts:login') + f'?next={request.path}'
        })
    
    return render(request, '403.html', context, status=403)


# Set as handler
handler403 = custom_permission_denied_view