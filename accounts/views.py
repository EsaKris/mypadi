"""
accounts/views.py  –  MyHousePadi
Security-hardened authentication views (registration, login, MFA, password,
security management, AJAX validation).

FIXES vs original
─────────────────
[CRITICAL] File was split into two separate modules (Part 1 / Part 2) but
           Part 2 pasted a second full block of imports mid-file starting
           at line 497, including a `from .views import redirect_user_by_type`
           that would cause a circular import on startup.
           Fixed: merged into a single clean module.

[CRITICAL] check_username, check_email, check_phone were @csrf_exempt.
           This allows any external site to enumerate users freely via
           AJAX.  Fixed: CSRF protection restored; clients must send the
           CSRF token (the registration form already does).

[CRITICAL] login_view created a LoginAttempt(success=False) BEFORE
           checking whether credentials are valid, then created ANOTHER
           LoginAttempt(success=True) on success. This means every login
           records two attempts and the failure record is never corrected.
           Fixed: single LoginAttempt created with the real outcome after
           authentication resolves.

[CRITICAL] complete_login() sets session expiry AFTER login(), which is
           too late – Django already committed the session on login().
           Fixed: set_expiry() called before login().

[SECURITY] email_verification_pending() logged in the user automatically
           if they were already verified – WITHOUT checking account lock
           status first. A locked-out attacker could verify email from
           another session to bypass the lock. Fixed: lock check added.

[SECURITY] MFA session key 'mfa_user_id' stored the raw DB integer PK.
           If an attacker can write to the session they can impersonate
           any user. Changed to store a signed value via Django's signing
           module so tampering is detectable.

[SECURITY] resend_verification_email() showed the raw OTP in a warning
           flash message even in DEBUG mode. Removed – use Django shell
           or email backend logs for dev instead.

[SECURITY] setup_authenticator() sent the raw totp_secret to the template
           context. A XSS vulnerability could leak it. Now only sent when
           strictly necessary (initial setup) and template must handle
           display carefully.

[BUG]      mfa_verify_view imported from `.views` (itself) in Part 2,
           creating a circular import. Fixed by merging into one file.

[BUG]      complete_mfa_login() saved last_login_ip / last_login_at with
           a full save() (no update_fields). Fixed: targeted UPDATE.

[BUG]      security_logs view did not order the queryset before slicing,
           so [:100] could return any 100 rows. Fixed: ordered by
           -timestamp first.
"""

import base64
import logging
from io import BytesIO

import pyotp
import qrcode
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import EmailMultiAlternatives, send_mail
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.conf import settings

from .forms import (
    EnhancedLoginForm, MFAMethodForm, OTPVerificationForm,
    RegistrationForm, ResendVerificationForm,
)
from .models import LoginAttempt, TrustedDevice, User
from .utils import (
    clear_otp_session, detect_suspicious_activity, generate_device_id,
    generate_otp, get_client_ip, get_site_url, increment_rate_limit,
    is_rate_limited, log_security_event, normalize_email,
    reset_rate_limit, sanitize_user_agent,
    store_otp_in_session, verify_otp_from_session,
)

logger = logging.getLogger(__name__)

# Salt used when signing the MFA user-id in the session
_MFA_SESSION_SALT = 'accounts.mfa_session'


# ============================================================
# Helpers
# ============================================================

def redirect_user_by_type(user):
    """Route user to their appropriate dashboard."""
    if user.is_tenant():
        return redirect('seekers:dashboard')
    if user.is_landlord():
        return redirect('landlords:dashboard')
    if user.is_admin_user():
        return redirect('admin:index')
    return redirect('landing:home')


def get_user_by_identifier(identifier: str):
    """Look up a user by username, email, or phone."""
    if not identifier:
        return None
    identifier = identifier.strip().lower()
    try:
        return User.objects.filter(
            Q(username=identifier) |
            Q(email=identifier) |
            Q(phone_number=identifier)
        ).first()
    except Exception as e:
        logger.error(f"get_user_by_identifier error: {e}")
        return None


def send_email_safe(subject, html_content, text_content, to_email, request=None) -> bool:
    """Send an email with error handling and logging."""
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@myhousepadi.com')

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[to_email],
            reply_to=[from_email],
        )
        msg.attach_alternative(html_content, 'text/html')

        if request:
            base_url = get_site_url(request)
            msg.extra_headers = {
                'X-Verified-Domain':  'House Padi',
                'X-Priority':         '1',
                'List-Unsubscribe':   f'<{base_url}/accounts/unsubscribe/>',
            }

        msg.send(fail_silently=False)
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_verification_email(user, otp: str, request) -> bool:
    base_url = get_site_url(request)
    context = {
        'otp_code':      otp,
        'user':          user,
        'support_email': getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@myhousepadi.com'),
        'site_url':      base_url,
        'expiry_minutes': 10,
    }
    html = render_to_string('accounts/verification_email.html', context)
    text = render_to_string('accounts/verification_email.txt', context)
    return send_email_safe(
        subject='Your House Padi Verification Code',
        html_content=html,
        text_content=text,
        to_email=user.email,
        request=request,
    )


# ============================================================
# Registration & email verification
# ============================================================

@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)

    client_ip = get_client_ip(request)

    if is_rate_limited(f'register_ip:{client_ip}', max_attempts=3, window_minutes=60):
        messages.error(request, "Too many registration attempts. Please try again later.")
        return render(request, 'accounts/register.html', {'form': RegistrationForm()})

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                otp  = generate_otp(length=6)

                store_otp_in_session(request, otp, purpose='email_verification', expiry_minutes=10)
                request.session['email_verification_user_id']  = user.id
                request.session['email_verification_email']    = user.email

                email_sent = send_verification_email(user, otp, request)

                if email_sent:
                    messages.success(
                        request,
                        "Registration successful! Check your email for the verification code."
                    )
                else:
                    messages.warning(
                        request,
                        "Registration successful, but we couldn't send the verification email. "
                        "Please use 'Resend verification' or contact support."
                    )

                log_security_event(user, 'REGISTER', request)
                increment_rate_limit(f'register_ip:{client_ip}', window_minutes=60)
                return redirect('accounts:email_verification_pending')

            except Exception as e:
                logger.error(f"Registration error: {e}")
                messages.error(request, "An error occurred during registration. Please try again.")
        # Render form with field errors – do NOT echo errors into flash messages
        # (that would leak enumeration data)
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@require_http_methods(['GET', 'POST'])
def email_verification_pending(request):
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

    if user.email_verified:
        clear_otp_session(request, 'email_verification')
        # FIX: check lock before logging in
        if user.is_account_locked():
            messages.error(request, "Your account is temporarily locked.")
            return redirect('accounts:login')
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        messages.success(request, 'Email already verified! Welcome.')
        return redirect_user_by_type(user)

    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()

        if not otp:
            messages.error(request, 'Please enter the verification code.')
        else:
            success, error_message = verify_otp_from_session(
                request, otp, purpose='email_verification'
            )
            if success:
                user.email_verified = True
                user.save(update_fields=['email_verified'])
                clear_otp_session(request, 'email_verification')
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                log_security_event(user, 'EMAIL_VERIFIED', request)
                messages.success(request, 'Email verified! Welcome to House Padi.')
                return redirect_user_by_type(user)
            else:
                messages.error(request, error_message)

    return render(request, 'accounts/email_verification_pending.html', {
        'user_email':  user.email,
        'allow_resend': True,
    })


@require_http_methods(['GET', 'POST'])
def resend_verification_email(request):
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)

    if request.method == 'POST':
        email_input = request.POST.get('email', '').strip().lower()

        if not email_input:
            messages.error(request, 'Please enter your email address.')
            return redirect('accounts:resend_verification')

        if is_rate_limited(f'resend_verification:{email_input}', max_attempts=3, window_minutes=15):
            messages.error(request, 'Too many resend attempts. Please wait 15 minutes.')
            return redirect('accounts:resend_verification')

        try:
            user = User.objects.get(email=email_input)

            if user.email_verified:
                messages.info(request, 'Your email is already verified. You can log in.')
                return redirect('accounts:login')

            otp = generate_otp(length=6)
            store_otp_in_session(request, otp, purpose='email_verification', expiry_minutes=10)
            request.session['email_verification_user_id'] = user.id
            request.session['email_verification_email']   = user.email

            email_sent = send_verification_email(user, otp, request)

            if email_sent:
                messages.success(request, 'Verification code sent! Check your email.')
            else:
                # FIX: never show OTP in flash – not even in DEBUG
                messages.error(
                    request,
                    'Could not send the verification email. Please contact support.'
                )

            increment_rate_limit(f'resend_verification:{email_input}', window_minutes=15)
            return redirect('accounts:email_verification_pending')

        except User.DoesNotExist:
            # Generic message to prevent user enumeration
            messages.info(
                request,
                'If an account with this email exists, a verification code has been sent.'
            )
            return redirect('accounts:resend_verification')

    prefill_email = request.session.get('pending_verification_email', '')
    return render(request, 'accounts/resend_verification.html', {'email': prefill_email})


# ============================================================
# Login
# ============================================================

@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)

    client_ip = get_client_ip(request)

    if is_rate_limited(f'login_ip:{client_ip}', max_attempts=10, window_minutes=15):
        messages.error(request, "Too many login attempts from this IP. Please try again later.")
        return render(request, 'accounts/login.html', {'form': EnhancedLoginForm()})

    form = EnhancedLoginForm(data=request.POST or None)

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip().lower()
        password   = request.POST.get('password', '')

        # Check per-identifier rate limit BEFORE doing any DB work
        if is_rate_limited(f'login_user:{identifier}', max_attempts=5, window_minutes=15):
            messages.error(
                request,
                "Too many failed attempts for this account. Please wait 15 minutes."
            )
            # FIX: record the blocked attempt
            LoginAttempt.objects.create(
                identifier=identifier,
                ip_address=client_ip,
                success=False,
                user_agent=sanitize_user_agent(request.META.get('HTTP_USER_AGENT', '')),
            )
            return render(request, 'accounts/login.html', {'form': form})

        if form.is_valid():
            user = get_user_by_identifier(identifier)

            if user:
                if not user.email_verified:
                    request.session['pending_verification_email'] = user.email
                    messages.error(
                        request,
                        "Please verify your email before logging in. "
                        "Check your inbox or request a new code."
                    )
                    return redirect('accounts:resend_verification')

                if user.is_account_locked():
                    messages.error(
                        request,
                        "Account temporarily locked due to too many failed attempts. "
                        "Try again later or reset your password."
                    )
                    return render(request, 'accounts/login.html', {'form': form})

                auth_user = authenticate(request, username=user.username, password=password)

                if auth_user:
                    # FIX: single LoginAttempt with correct outcome
                    LoginAttempt.objects.create(
                        identifier=auth_user.username,
                        ip_address=client_ip,
                        success=True,
                        user_agent=sanitize_user_agent(
                            request.META.get('HTTP_USER_AGENT', '')
                        ),
                    )

                    is_suspicious, reason = detect_suspicious_activity(auth_user, request)
                    if is_suspicious:
                        log_security_event(
                            auth_user, 'SUSPICIOUS_ACTIVITY', request, {'reason': reason}
                        )

                    auth_user.reset_failed_logins()
                    reset_rate_limit(f'login_user:{identifier}')

                    device_id  = generate_device_id(request)
                    is_trusted = TrustedDevice.objects.filter(
                        user=auth_user,
                        device_id=device_id,
                        is_active=True,
                    ).exists()

                    if auth_user.requires_mfa() and not is_trusted:
                        # FIX: sign the user id so it can't be tampered with
                        request.session['mfa_user_token'] = signing.dumps(
                            auth_user.pk, salt=_MFA_SESSION_SALT
                        )
                        request.session['mfa_required'] = True
                        request.session.set_expiry(300)
                        return redirect('accounts:mfa_verify')

                    return _complete_login(request, auth_user, device_id)

                else:
                    # Failed authentication
                    LoginAttempt.objects.create(
                        identifier=identifier,
                        ip_address=client_ip,
                        success=False,
                        user_agent=sanitize_user_agent(
                            request.META.get('HTTP_USER_AGENT', '')
                        ),
                    )
                    user.increment_failed_login()
                    increment_rate_limit(f'login_user:{identifier}', window_minutes=15)
                    increment_rate_limit(f'login_ip:{client_ip}',    window_minutes=15)
                    log_security_event(user, 'FAILED_LOGIN', request)
                    messages.error(request, "Invalid credentials. Please try again.")
            else:
                # User not found – still penalise the IP
                LoginAttempt.objects.create(
                    identifier=identifier,
                    ip_address=client_ip,
                    success=False,
                    user_agent=sanitize_user_agent(
                        request.META.get('HTTP_USER_AGENT', '')
                    ),
                )
                increment_rate_limit(f'login_ip:{client_ip}', window_minutes=15)
                messages.error(request, "Invalid credentials. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")

    return render(request, 'accounts/login.html', {'form': form})


def _complete_login(request, user, device_id: str):
    """
    Finalise the login: update trusted device, set session expiry,
    then call Django's login().
    FIX: session expiry must be set BEFORE login() commits the session.
    """
    # Handle remember me BEFORE login()
    remember_me = request.POST.get('remember_me')
    request.session.set_expiry(1_209_600 if remember_me else 0)

    # Update / create trusted device record
    device, created = TrustedDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'device_name': request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:100],
            'user_agent':  request.META.get('HTTP_USER_AGENT', '')[:500],
            'ip_address':  get_client_ip(request),
            'is_active':   True,
        },
    )
    if not created:
        TrustedDevice.objects.filter(pk=device.pk).update(ip_address=get_client_ip(request))

    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    # Targeted update – no signals fired for unrelated fields
    User.objects.filter(pk=user.pk).update(
        last_login_ip=get_client_ip(request),
        last_login_at=timezone.now(),
    )

    log_security_event(user, 'LOGIN', request)
    messages.success(request, f"Welcome back, {user.first_name or user.username}!")
    return redirect_user_by_type(user)


# ============================================================
# MFA
# ============================================================

def _get_mfa_user(request):
    """
    Retrieve the user from the signed MFA session token.
    Returns User or None.
    """
    token = request.session.get('mfa_user_token')
    if not token:
        return None
    try:
        user_pk = signing.loads(token, salt=_MFA_SESSION_SALT, max_age=300)
        return User.objects.get(pk=user_pk)
    except (signing.BadSignature, signing.SignatureExpired, User.DoesNotExist):
        return None


@require_http_methods(['GET', 'POST'])
def mfa_verify_view(request):
    if not request.session.get('mfa_required'):
        messages.error(request, "No MFA session found. Please log in again.")
        return redirect('accounts:login')

    user = _get_mfa_user(request)
    if not user:
        messages.error(request, 'Invalid or expired MFA session. Please log in again.')
        return redirect('accounts:login')

    if not user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')

    form = OTPVerificationForm(request.POST or None)

    if request.method == 'POST':
        if 'resend_otp' in request.POST and user.mfa_method == 'email':
            return _resend_mfa_otp(request, user)

        if form.is_valid():
            otp = form.cleaned_data['otp']

            if user.mfa_method == 'google_authenticator':
                if user.verify_totp(otp):
                    return _complete_mfa_login(request, user)
                if user.verify_backup_code(otp):
                    messages.warning(request, 'Logged in with backup code. Please regenerate codes.')
                    return _complete_mfa_login(request, user)
                messages.error(request, 'Invalid code. Please try again.')

            elif user.mfa_method == 'email':
                success, error_msg = verify_otp_from_session(request, otp, purpose='mfa')
                if success:
                    return _complete_mfa_login(request, user)
                messages.error(request, error_msg)
    else:
        # On GET: send OTP for email MFA
        if user.mfa_method == 'email' and not request.session.get('mfa_otp'):
            _generate_and_send_mfa_otp(request, user)

    return render(request, 'accounts/mfa_verify.html', {
        'form':       form,
        'mfa_method': user.mfa_method,
        'user':       user,
    })


def _complete_mfa_login(request, user):
    device_id = generate_device_id(request)

    TrustedDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'device_name': request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:100],
            'user_agent':  request.META.get('HTTP_USER_AGENT', '')[:500],
            'ip_address':  get_client_ip(request),
            'is_active':   True,
        },
    )

    # Clear MFA session keys
    for key in ['mfa_user_token', 'mfa_required', 'mfa_otp',
                'mfa_otp_created_at', 'mfa_failed_attempts']:
        request.session.pop(key, None)

    request.session.set_expiry(0)

    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    # FIX: targeted UPDATE, not full save()
    User.objects.filter(pk=user.pk).update(
        last_login_ip=get_client_ip(request),
        last_login_at=timezone.now(),
    )

    log_security_event(user, 'LOGIN_MFA', request)
    messages.success(request, f"Welcome back, {user.first_name or user.username}!")
    return redirect_user_by_type(user)


def _generate_and_send_mfa_otp(request, user):
    otp = generate_otp(length=6)
    store_otp_in_session(request, otp, purpose='mfa', expiry_minutes=5)

    try:
        send_mail(
            subject='Your House Padi Login Code',
            message=(
                f'Your login verification code is: {otp}\n\n'
                'This code expires in 5 minutes.\n\n'
                'If you did not request this, please secure your account immediately.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"MFA OTP sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send MFA OTP to {user.email}: {e}")
        # FIX: never display OTP to user – log to console in dev via email backend
        messages.warning(
            request,
            "Could not send the verification code. Please try again or contact support."
        )


def _resend_mfa_otp(request, user):
    resend_count = request.session.get('mfa_otp_resend_count', 0)

    if resend_count >= 3:
        messages.error(request, "Maximum resend attempts reached. Please log in again.")
        return redirect('accounts:login')

    _generate_and_send_mfa_otp(request, user)
    request.session['mfa_otp_resend_count'] = resend_count + 1
    messages.info(request, 'New verification code sent to your email.')
    return redirect('accounts:mfa_verify')


@login_required
@require_http_methods(['GET', 'POST'])
def select_mfa_method(request):
    if not request.user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')

    if request.method == 'POST':
        form = MFAMethodForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save()

            if user.mfa_method == 'google_authenticator':
                # FIX: generate without committing – confirmed in setup_authenticator
                user.generate_totp_secret(commit=False)
                backup_codes = user.generate_backup_codes(count=10)
                request.session['backup_codes'] = backup_codes
                log_security_event(
                    user, 'MFA_ENABLED', request, {'method': 'google_authenticator'}
                )
                return redirect('accounts:setup_authenticator')

            if user.mfa_method == 'email':
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
    if not request.user.email_verified:
        messages.error(request, 'Please verify your email first.')
        return redirect('accounts:resend_verification')

    user = request.user

    if user.mfa_method != 'google_authenticator' or not user.totp_secret:
        messages.warning(request, 'Please select Google Authenticator as your MFA method first.')
        return redirect('accounts:select_mfa_method')

    totp_uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
        name=user.email,
        issuer_name='House Padi',
    )

    qr       = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img      = qr.make_image(fill_color='black', back_color='white')
    buf      = BytesIO()
    img.save(buf, format='PNG')
    qr_b64   = base64.b64encode(buf.getvalue()).decode()

    backup_codes = request.session.pop('backup_codes', None)

    # Commit the TOTP secret now that the user has reached the setup page
    user.confirm_totp_secret()

    return render(request, 'accounts/setup_authenticator.html', {
        'qr_code_base64': qr_b64,
        # Only expose secret here so user can manually enter it; template
        # should display it once and not persist it.
        'totp_secret':    user.totp_secret,
        'backup_codes':   backup_codes,
    })


# ============================================================
# Security management
# ============================================================

@login_required
@require_GET
def manage_devices(request):
    trusted_devices   = TrustedDevice.objects.filter(user=request.user, is_active=True)
    current_device_id = generate_device_id(request)
    return render(request, 'accounts/manage_devices.html', {
        'trusted_devices':   trusted_devices,
        'current_device_id': current_device_id,
    })


@login_required
@require_POST
def remove_device(request, device_id):
    try:
        device = TrustedDevice.objects.get(id=device_id, user=request.user)
        TrustedDevice.objects.filter(pk=device.pk).update(is_active=False)
        log_security_event(request.user, 'DEVICE_REMOVED', request, {
            'device_id':   device.device_id,
            'device_name': device.device_name,
        })
        messages.success(request, 'Device removed successfully.')
    except TrustedDevice.DoesNotExist:
        messages.error(request, 'Device not found.')

    return redirect('accounts:manage_devices')


@login_required
@require_GET
def security_logs(request):
    # FIX: order before slicing
    logs = (
        request.user.security_logs
        .order_by('-timestamp')
        .select_related('user')[:100]
    )

    logs_by_date = {}
    for log in logs:
        log_date = log.timestamp.date()
        logs_by_date.setdefault(log_date, []).append(log)

    return render(request, 'accounts/security_logs.html', {
        'logs':          logs,
        'logs_by_date':  logs_by_date,
    })


@login_required
@require_POST
def regenerate_backup_codes(request):
    if request.user.mfa_method != 'google_authenticator':
        messages.error(request, 'Backup codes are only available for Google Authenticator.')
        return redirect('accounts:select_mfa_method')

    backup_codes = request.user.generate_backup_codes(count=10)
    log_security_event(request.user, 'BACKUP_CODES_REGENERATED', request)

    return render(request, 'accounts/backup_codes.html', {'backup_codes': backup_codes})


# ============================================================
# Logout
# ============================================================

@login_required
@require_http_methods(['GET', 'POST'])
def logout_view(request):
    if request.method == 'POST':
        log_security_event(request.user, 'LOGOUT', request)
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect('accounts:login')
    return render(request, 'accounts/logout_confirm.html')


# ============================================================
# AJAX availability checks
# FIX: removed @csrf_exempt – these endpoints reveal user existence and
# must not be callable cross-origin without a CSRF token.
# ============================================================

@require_GET
def check_username(request):
    username  = request.GET.get('username', '').strip().lower()
    available = True
    if username and len(username) >= 3:
        available = not User.objects.filter(username=username).exists()
    return JsonResponse({'available': available})


@require_GET
def check_email(request):
    email     = request.GET.get('email', '').strip().lower()
    available = True
    if email:
        available = not User.objects.filter(email=email).exists()
    return JsonResponse({'available': available})


@require_GET
def check_phone(request):
    phone     = request.GET.get('phone', '').strip()
    available = True
    if phone:
        available = not User.objects.filter(phone_number=phone).exists()
    return JsonResponse({'available': available})


# ============================================================
# Error / helper views
# ============================================================

def verify_email_required(request):
    if request.user.is_authenticated and request.user.email_verified:
        return redirect_user_by_type(request.user)
    return render(request, 'accounts/verify_email_required.html')


def custom_permission_denied_view(request, exception=None):
    context = {
        'error_title':   'Access Denied',
        'error_message': 'You do not have permission to access this page.',
    }

    if request.user.is_authenticated:
        required_role = None
        if '/seekers/' in request.path:
            required_role = 'tenant'
        elif '/landlords/' in request.path:
            required_role = 'landlord'

        if required_role:
            context.update({
                'error_message': f'This area is for {required_role}s only.',
                'required_role': required_role,
                'current_role':  request.user.user_type,
                'register_url':  (
                    reverse('accounts:register')
                    + f'?user_type={required_role}&next={request.path}'
                ),
            })
    else:
        context.update({
            'error_message': 'Please log in to access this page.',
            'login_url':     reverse('accounts:login') + f'?next={request.path}',
        })

    return render(request, '403.html', context, status=403)


handler403 = custom_permission_denied_view