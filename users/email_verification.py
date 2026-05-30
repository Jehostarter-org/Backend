import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailVerificationCode

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = getattr(settings, 'EMAIL_OTP_EXPIRY_MINUTES', 15)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def generate_otp() -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(OTP_LENGTH))


def issue_verification_code(user) -> str:
    """Create a new OTP for the user, invalidate older codes, return plain OTP."""
    EmailVerificationCode.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=timezone.now())

    plain = generate_otp()
    EmailVerificationCode.objects.create(
        user=user,
        code_hash=_hash_code(plain),
        expires_at=timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    )
    return plain


def send_verification_email(user) -> None:
    """Generate OTP and send styled HTML email."""
    import logging
    from django.conf import settings

    logger = logging.getLogger(__name__)
    plain = issue_verification_code(user)
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    verify_url = f'{frontend_url}/auth/verify-email'

    context = {
        'first_name': user.first_name or user.username,
        'otp_code': plain,
        'expiry_minutes': OTP_EXPIRY_MINUTES,
        'verify_url': verify_url,
        'year': timezone.now().year,
    }

    html_body = render_to_string('users/email/verification_otp.html', context)
    text_body = (
        f'Hi {context["first_name"]},\n\n'
        f'Your Jehostarter verification code is: {plain}\n\n'
        f'This code expires in {OTP_EXPIRY_MINUTES} minutes.\n'
        f'Enter it at: {verify_url}\n\n'
        f'If you did not sign up, ignore this email.'
    )

    subject = f'Your Jehostarter verification code: {plain}'
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    msg = EmailMultiAlternatives(subject, text_body, from_email, to_email)
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=False)

    backend = settings.EMAIL_BACKEND
    if 'console' in backend:
        logger.warning(
            'Verification email for %s was printed to the console only. '
            'Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in backend/.env for real delivery. '
            'See backend/.env.email.example',
            user.email,
        )
    else:
        logger.info('Verification email sent to %s via %s', user.email, backend)


def verify_code(user, code: str) -> tuple[bool, str]:
    """
    Validate OTP for user. Returns (success, error_message).
    Marks user verified on success.
    """
    normalized = (code or '').strip().replace(' ', '')
    if not normalized or len(normalized) != OTP_LENGTH or not normalized.isdigit():
        return False, 'Enter a valid 6-digit code.'

    record = (
        EmailVerificationCode.objects
        .filter(user=user, used_at__isnull=True)
        .order_by('-created_at')
        .first()
    )

    if not record:
        return False, 'No active verification code. Request a new one.'

    if record.is_expired:
        return False, 'This code has expired. Request a new one.'

    if record.attempts >= record.max_attempts:
        return False, 'Too many attempts. Request a new code.'

    if _hash_code(normalized) != record.code_hash:
        record.attempts += 1
        record.save(update_fields=['attempts'])
        remaining = record.max_attempts - record.attempts
        if remaining <= 0:
            return False, 'Too many attempts. Request a new code.'
        return False, f'Incorrect code. {remaining} attempt(s) left.'

    record.used_at = timezone.now()
    record.save(update_fields=['used_at'])

    user.is_verified = True
    user.verified_at = timezone.now()
    user.save(update_fields=['is_verified', 'verified_at'])

    return True, 'Email verified successfully.'
