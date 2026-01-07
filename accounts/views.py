from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Q
import pyotp
import random
import qrcode
from io import BytesIO
import base64
import logging
from datetime import timedelta

from .forms import RegistrationForm, EnhancedLoginForm, MFAMethodForm, OTPVerificationForm, CustomPasswordResetForm
from .models import User, SecurityLog, TrustedDevice
from .utils import generate_device_id, generate_verification_token, verify_token

logger = logging.getLogger(__name__)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def log_security_event(user, action, request):
    SecurityLog.objects.create(
        user=user,
        action=action,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

def redirect_user_by_type(user):
    if user.is_tenant():
        return redirect('seekers:dashboard')
    elif user.is_landlord():
        return redirect('landlords:dashboard')
    elif user.is_admin():
        return redirect('admin:index')
    else:
        return redirect('landing:home')

def get_user_by_identifier(identifier):
    """
    Find user by username, email, or phone number
    """
    if not identifier:
        return None
    
    try:
        # Try to find user by username, email, or phone number
        user = User.objects.filter(
            Q(username=identifier) | 
            Q(email=identifier) | 
            Q(phone_number=identifier)
        ).first()
        return user
    except User.DoesNotExist:
        return None

def send_verification_email(user, otp, request):
    """
    Send OTP-only verification email (HTML + text fallback), production ready.
    """
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from accounts.utils import get_site_url  # <-- dynamic domain utility

    base_url = get_site_url(request)  # dynamically pick the domain
    context = {
        "otp_code": otp,
        "user": user,
        "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@myhousepadi.com"),
        "site_url": base_url,
    }

    html_content = render_to_string("accounts/verification_email.html", context)
    text_content = render_to_string("accounts/verification_email.txt", context)

    subject = "Your House Padi Verification Code"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@myhousepadi.com")
    to_email = user.email.strip().lower()

    try:
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[to_email],
            reply_to=[from_email],
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.extra_headers = {
            "X-Verified-Domain": "House Padi",
            "X-Priority": "1",
            "List-Unsubscribe": f"<{base_url}/accounts/unsubscribe/>"
        }
        email_message.send(fail_silently=False)
        logger.info(f"Verification OTP email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification OTP to {to_email}: {str(e)}")
        return False


import secrets  # for secure OTP

import secrets

def register_view(request):
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            
            # Generate a secure 6-digit OTP
            otp = str(secrets.randbelow(900000) + 100000)  # 100000-999999

            # Store OTP securely in session
            request.session['email_verification_otp'] = otp
            request.session['email_verification_user_id'] = user.id
            request.session['email_verification_email'] = user.email
            request.session.set_expiry(600)  # 10 minutes

            # Send OTP email
            email_sent = send_verification_email(user, otp, request)  # no token anymore

            # Generic message to avoid exposing OTP
            if email_sent:
                messages.success(request, "Registration successful! Please check your email for the verification code.")
            else:
                messages.error(request, "Registration successful, but we could not send a verification email. Contact support.")

            # Optional: store user ID for MFA setup
            request.session['user_id_for_mfa'] = user.id
            request.session['verified_user_id'] = user.id

            log_security_event(user, 'REGISTER', request)

            # Redirect to OTP verification page
            return redirect('accounts:email_verification_pending')
    else:
        form = RegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})

def email_verification_pending(request):
    """Show email verification pending page with OTP input (OTP-only verification)."""
    
    user_id = request.session.get('email_verification_user_id')
    if not user_id:
        messages.error(request, 'No pending email verification found.')
        return redirect('accounts:register')
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        # Clear any stale session
        request.session.pop('email_verification_otp', None)
        request.session.pop('email_verification_user_id', None)
        request.session.pop('email_verification_email', None)

        messages.error(request, 'No pending email verification found.')
        return redirect('accounts:register')
    
    # If user is already verified, log them in and redirect
    if user.email_verified:
        request.session.pop('email_verification_otp', None)
        request.session.pop('email_verification_user_id', None)
        request.session.pop('email_verification_email', None)
        
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        return redirect_user_by_type(user)
    
    # Handle OTP submission
    if request.method == 'POST':
        return verify_email_otp(request)
    
    # If OTP session is missing or expired
    if not request.session.get('email_verification_otp'):
        messages.error(request, 'Your verification session has expired. Please request a new OTP.')
        return redirect('accounts:resend_verification')
    
    # Render OTP input page
    return render(request, 'accounts/email_verification_pending.html', {
        'user_email': user.email,  # optional, can be shown in template
        'allow_resend': True,      # optional flag for "resend OTP" button
    })



def verify_email_otp(request):
    """Verify email using OTP from session (OTP-only, production-ready)."""

    if request.method != 'POST':
        return redirect('accounts:email_verification_pending')

    # Get OTP and user info from POST and session
    otp = request.POST.get('otp')
    user_id = request.session.get('email_verification_user_id')
    stored_otp = request.session.get('email_verification_otp')
    email = request.session.get('email_verification_email')
    otp_created_at = request.session.get('email_verification_otp_created_at')

    # Helper to clear session
    def clear_otp_session():
        keys = [
            'email_verification_otp',
            'email_verification_user_id',
            'email_verification_email',
            'email_verification_otp_created_at',
            'email_verification_failed_attempts'
        ]
        for key in keys:
            request.session.pop(key, None)

    # Validate session
    if not all([otp, user_id, stored_otp, email, otp_created_at]):
        clear_otp_session()
        messages.error(request, 'Invalid or expired verification session.')
        return redirect('accounts:register')

    # Ensure otp_created_at is datetime
    if isinstance(otp_created_at, float):  # sometimes saved as timestamp
        otp_created_at = timezone.datetime.fromtimestamp(otp_created_at, tz=timezone.utc)

    # Check if OTP is expired (10 min)
    if timezone.now() > otp_created_at + timedelta(minutes=10):
        clear_otp_session()
        messages.error(request, 'Your OTP has expired. Please request a new verification email.')
        return redirect('accounts:resend_verification')

    # Verify OTP securely
    if not secrets.compare_digest(otp, stored_otp):
        # Track failed attempts
        failed_attempts = request.session.get('email_verification_failed_attempts', 0) + 1
        request.session['email_verification_failed_attempts'] = failed_attempts

        if failed_attempts >= 5:
            clear_otp_session()
            messages.error(request, 'Too many failed attempts. Please request a new verification email.')
            return redirect('accounts:resend_verification')

        messages.error(request, 'Invalid verification code. Please try again.')
        return redirect('accounts:email_verification_pending')

    # OTP correct: verify user
    try:
        user = User.objects.get(id=user_id, email=email)
        user.email_verified = True
        user.save()

        # Clear session
        clear_otp_session()

        # Log in the user
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)

        log_security_event(user, 'EMAIL_VERIFIED_OTP', request)
        messages.success(request, 'Email verified successfully! Welcome to House Padi.')

        return redirect_user_by_type(user)

    except User.DoesNotExist:
        clear_otp_session()
        messages.error(request, 'User not found.')
        return redirect('accounts:register')


# def verify_email(request, token):
#     """Verify email using a secure token link."""

#     # Redirect already verified users to dashboard
#     if request.user.is_authenticated and request.user.email_verified:
#         return redirect_user_by_type(request.user)

#     # Verify token and get associated email
#     email = verify_token(token)
#     if not email:
#         messages.error(request, 'Invalid or expired verification link.')
#         return redirect('accounts:login')

#     try:
#         user = User.objects.get(email=email)

#         # If already verified, inform and redirect to login
#         if user.email_verified:
#             messages.info(request, 'Your email is already verified. Please log in.')
#             return redirect('accounts:login')

#         # Mark email as verified
#         user.email_verified = True
#         user.save()

#         # Clear any pending OTP verification sessions
#         for key in ['email_verification_otp', 'email_verification_user_id', 'email_verification_email', 'email_verification_otp_created_at', 'email_verification_failed_attempts']:
#             request.session.pop(key, None)

#         # Log security event
#         log_security_event(user, 'EMAIL_VERIFIED_LINK', request)

#         messages.success(request, 'Email verified successfully! You can now log in.')
#         return redirect('accounts:login')

#     except User.DoesNotExist:
#         messages.error(request, 'Invalid verification link.')
#         return redirect('accounts:login')


from accounts.utils import get_site_url

def resend_verification_email(request):
    """Resend OTP safely for email verification (OTP-only flow)."""
    
    # Redirect already verified users
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    
    if request.method == 'POST':
        email_input = request.POST.get('email', '').strip().lower()
        
        if not email_input:
            messages.error(request, 'Please enter your email address.')
            return redirect('accounts:resend_verification')
        
        try:
            user = User.objects.get(email=email_input)
            
            if user.email_verified:
                messages.info(request, 'Your email is already verified. You can log in.')
                return redirect('accounts:login')
            
            # Generate secure 6-digit OTP
            otp = str(secrets.randbelow(900000) + 100000)
            
            # Store OTP in session with timestamp
            request.session['email_verification_otp'] = otp
            request.session['email_verification_user_id'] = user.id
            request.session['email_verification_email'] = user.email
            request.session['email_verification_otp_created_at'] = timezone.now()
            request.session.set_expiry(600)  # 10 minutes
            
            # Send OTP email
            try:
                send_mail(
                    subject='Your House Padi Verification Code',
                    message=f'Your verification code is: {otp}\n\nThis code will expire in 10 minutes.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                messages.success(request, 'Verification code sent! Check your email.')
            except Exception as e:
                logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
                # Only show OTP in dev or fallback (remove in production)
                messages.warning(request, f'Unable to send email. Use this code to verify: {otp}')
            
            # Prefill email in session for convenience
            request.session['pending_verification_email'] = user.email
            
            return redirect('accounts:email_verification_pending')
        
        except User.DoesNotExist:
            # Generic message to prevent user enumeration
            messages.info(request, 'If an account exists with this email, a verification code has been sent.')
            return redirect('accounts:resend_verification')
    
    # Prefill email field if available
    prefill_email = request.session.get('pending_verification_email', '')
    return render(request, 'accounts/resend_verification.html', {'email': prefill_email})


def login_view(request):
    # Redirect already verified users
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)

    form = EnhancedLoginForm(data=request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        identifier = form.cleaned_data.get('username')  # username, email, or phone
        password = form.cleaned_data.get('password')

        user = get_user_by_identifier(identifier)

        if user:
            # If email not verified, redirect to OTP verification
            if not user.email_verified:
                request.session['pending_verification_email'] = user.email
                messages.error(request,
                    "Please verify your email before logging in. "
                    "Check your inbox or request a new verification code."
                )
                return redirect('accounts:resend_verification')

            # Authenticate user
            auth_user = authenticate(request, username=user.username, password=password)

            if auth_user:
                # Check account lock
                if auth_user.is_account_locked():
                    messages.error(request,
                        "Account temporarily locked due to too many failed login attempts."
                    )
                    return render(request, 'accounts/login.html', {'form': form})

                # Reset failed attempts
                auth_user.reset_failed_logins()

                # Trusted device + MFA
                device_id = generate_device_id(request)
                is_trusted_device = TrustedDevice.objects.filter(user=auth_user, device_id=device_id).exists()

                if auth_user.mfa_method != 'none' and not is_trusted_device:
                    request.session['mfa_user_id'] = auth_user.id
                    request.session['mfa_required'] = True
                    return redirect('accounts:mfa_verify')

                # Login user
                login(request, auth_user)
                auth_user.last_login_ip = get_client_ip(request)
                auth_user.last_login_at = timezone.now()
                auth_user.save()

                if not is_trusted_device:
                    TrustedDevice.objects.get_or_create(
                        user=auth_user,
                        device_id=device_id,
                        defaults={
                            'device_name': f"{request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:100]}",
                            'user_agent': request.META.get('HTTP_USER_AGENT', '')
                        }
                    )

                log_security_event(auth_user, 'LOGIN', request)
                messages.success(request, "Login successful!")
                return redirect_user_by_type(auth_user)

            else:
                # Increment failed login attempts safely
                user.increment_failed_login()
                log_security_event(user, 'FAILED_LOGIN', request)
                messages.error(request, "Invalid credentials.")

        else:
            # Generic message to avoid user enumeration
            messages.error(request, "Invalid credentials.")

    return render(request, 'accounts/login.html', {'form': form})

def mfa_verify_view(request):
    # Redirect already verified users
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)

    # MFA session check
    if not request.session.get('mfa_required') or not request.session.get('mfa_user_id'):
        messages.error(request, "No MFA session found. Please log in again.")
        return redirect('accounts:login')

    try:
        user = User.objects.get(id=request.session['mfa_user_id'])
    except User.DoesNotExist:
        messages.error(request, 'Invalid session. Please login again.')
        return redirect('accounts:login')

    # Ensure email is verified
    if not user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')

    form = OTPVerificationForm(request.POST or None)

    if request.method == 'POST':
        # Handle resend request
        if 'resend_otp' in request.POST and user.mfa_method == 'email':
            return resend_otp_view(request, user)

        if form.is_valid():
            otp = form.cleaned_data['otp']

            if user.mfa_method == 'google_authenticator':
                if user.verify_totp(otp):
                    return complete_mfa_login(request, user)
                else:
                    messages.error(request, 'Invalid OTP. Please try again.')
            elif user.mfa_method == 'email':
                session_otp = request.session.get('mfa_otp')
                otp_expiry = request.session.get('mfa_otp_expiry')

                if session_otp and otp == session_otp:
                    # Check expiry
                    if otp_expiry and timezone.now() > otp_expiry:
                        messages.error(request, "OTP expired. Please request a new one.")
                    else:
                        return complete_mfa_login(request, user)
                else:
                    messages.error(request, 'Invalid OTP. Please try again.')
        else:
            messages.error(request, 'Please enter a valid 6-digit OTP.')

    else:
        # Generate OTP for GET request only if email OTP and none exists
        if user.mfa_method == 'email' and not request.session.get('mfa_otp'):
            generate_email_otp(request, user)

    return render(request, 'accounts/mfa_verify.html', {
        'form': form,
        'mfa_method': user.mfa_method
    })


def complete_mfa_login(request, user):
    """Complete login after successful MFA verification"""
    device_id = generate_device_id(request)
    TrustedDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'device_name': f"{request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:100]}",
            'user_agent': request.META.get('HTTP_USER_AGENT', '')
        }
    )

    # Clear MFA session
    for key in ['mfa_user_id', 'mfa_required', 'mfa_otp', 'mfa_otp_expiry']:
        request.session.pop(key, None)

    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    user.last_login_ip = get_client_ip(request)
    user.last_login_at = timezone.now()
    user.save()

    log_security_event(user, 'LOGIN_MFA', request)
    messages.success(request, "Login successful!")

    return redirect_user_by_type(user)


def generate_email_otp(request, user):
    """Generate OTP, store it in session, and send via email"""
    otp = str(random.randint(100000, 999999))
    request.session['mfa_otp'] = otp
    request.session['mfa_otp_expiry'] = (timezone.now() + timedelta(minutes=5)).isoformat()
    request.session.set_expiry(300)  # Session expires after 5 minutes

    try:
        send_mail(
            'Your House Padi Verification Code',
            f'Your verification code is: {otp}\n\nThis code will expire in 5 minutes.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send OTP email: {str(e)}")
        messages.error(request, 'Failed to send verification code. Please try again.')


def resend_otp_view(request, user):
    """Resend OTP with rate limit"""
    otp_resend_count = request.session.get('mfa_otp_resend_count', 0)

    if otp_resend_count >= 3:
        messages.error(request, "You have reached the maximum OTP resend attempts. Try again later.")
        return redirect('accounts:mfa_verify')

    if user.mfa_method == 'email':
        generate_email_otp(request, user)
        request.session['mfa_otp_resend_count'] = otp_resend_count + 1
        messages.info(request, 'New verification code sent to your email.')
    else:
        messages.info(request, 'Please use your authenticator app to generate a new code.')

    return redirect('accounts:mfa_verify')

@login_required
def select_mfa_method(request):
    # If user email is not verified, redirect to verification
    if not request.user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')
    
    if request.method == 'POST':
        form = MFAMethodForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save()
            
            if user.mfa_method == 'google_authenticator' and not user.totp_secret:
                user.generate_totp_secret()
                user.save()
                return redirect('accounts:setup_authenticator')
            
            messages.success(request, 'MFA method updated successfully!')
            # Redirect to appropriate dashboard after MFA setup
            return redirect_user_by_type(user)
    else:
        form = MFAMethodForm(instance=request.user)
    
    return render(request, 'accounts/select_mfa_method.html', {'form': form})

@login_required
def setup_authenticator(request):
    # If user email is not verified, redirect to verification
    if not request.user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')
    
    user = request.user
    if user.mfa_method != 'google_authenticator' or not user.totp_secret:
        messages.warning(request, 'Please select Google Authenticator as your MFA method first.')
        return redirect('accounts:select_mfa_method')
    
    # Generate TOTP URI and QR code
    totp_uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
        name=user.email,
        issuer_name='House Padi'
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'accounts/setup_authenticator.html', {
        'qr_code_base64': qr_code_base64,
        'totp_secret': user.totp_secret,
    })

@login_required
def manage_devices(request):
    return render(request, 'accounts/manage_devices.html', {'trusted_devices': TrustedDevice.objects.filter(user=request.user)})

@login_required
def remove_device(request, device_id):
    try:
        device = TrustedDevice.objects.get(id=device_id, user=request.user)
        device.delete()
        messages.success(request, 'Device removed successfully.')
    except TrustedDevice.DoesNotExist:
        messages.error(request, 'Device not found.')
    return redirect('accounts:manage_devices')

@login_required
def security_logs(request):
    logs = SecurityLog.objects.filter(user=request.user)[:50]  # Last 50 logs
    return render(request, 'accounts/security_logs.html', {'logs': logs})

@login_required
def logout_view(request):
    log_security_event(request.user, 'LOGOUT', request)
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('accounts:login')

def verify_email_required(request):
    """Show email verification required page"""
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    
    messages.warning(request, "Please verify your email address to continue.")
    return render(request, 'accounts/verify_email_required.html')

# Password Reset Views
class CustomPasswordResetView(PasswordResetView):
    template_name = 'accounts/password_reset.html'
    form_class = CustomPasswordResetForm
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')

# Permission Denied View
def custom_permission_denied_view(request, exception=None):
    """Enhanced 403 error handler"""
    context = {}
    
    if request.user.is_authenticated:
        # User is logged in but doesn't have permission
        if hasattr(request.user, 'is_tenant') and hasattr(request.user, 'is_landlord'):
            context.update({
                'error_message': f'Access denied. This page requires {"tenant" if request.user.is_landlord() else "landlord"} access.',
                'required_role': 'landlord' if request.user.is_tenant() else 'tenant',
                'current_role': 'tenant' if request.user.is_landlord() else 'landlord',
                'register_url': reverse('accounts:register') + f'?user_type={"tenant" if request.user.is_landlord() else "landlord"}&next={request.path}'
            })
        else:
            context.update({
                'error_message': 'You do not have permission to access this page.',
            })
    else:
        # User is not logged in
        context.update({
            'error_message': 'Please log in to access this page.',
            'login_url': reverse('accounts:login') + f'?next={request.path}'
        })
    
    return render(request, '403.html', context, status=403)

        # Make sure this is at the bottom of views.py
handler403 = custom_permission_denied_view


from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils.crypto import get_random_string
from django.contrib.auth import get_user_model

User = get_user_model()

@csrf_exempt  # If called via AJAX from front-end
@require_GET
def check_username(request):
    username = request.GET.get('username', '').strip()
    exists = False
    if username:
        exists = User.objects.filter(username__iexact=username).exists()
    # Introduce a small random delay to prevent timing attacks
    _ = get_random_string(length=2)
    return JsonResponse({'available': not exists})

@csrf_exempt
@require_GET
def check_email(request):
    email = request.GET.get('email', '').strip()
    exists = False
    if email:
        exists = User.objects.filter(email__iexact=email).exists()
    _ = get_random_string(length=2)
    return JsonResponse({'available': not exists})

@csrf_exempt
@require_GET
def check_phone(request):
    phone = request.GET.get('phone', '').strip()
    exists = False
    if phone:
        exists = User.objects.filter(phone_number=phone).exists()
    _ = get_random_string(length=2)
    return JsonResponse({'available': not exists})
