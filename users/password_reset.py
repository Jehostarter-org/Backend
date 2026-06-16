import hashlib
import secrets
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import PasswordResetToken

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_MINUTES = getattr(settings, 'PASSWORD_RESET_EXPIRY_MINUTES', 30)


def _hash_token(token: str) -> str:
    """SHA-256 hash of the plaintext token (stored in DB)."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generate_reset_token(user) -> str:
    """
    Generate a cryptographically secure reset token, invalidate any
    unused tokens for this user, store the hash, return the plain token.
    """
    PasswordResetToken.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=timezone.now())

    plain = secrets.token_urlsafe(32)
    PasswordResetToken.objects.create(
        user=user,
        token_hash=_hash_token(plain),
        expires_at=timezone.now() + timedelta(minutes=TOKEN_EXPIRY_MINUTES),
    )
    return plain


def send_password_reset_email(user) -> None:
    """Generate a reset token and send a styled HTML email with the reset link."""
    plain_token = generate_reset_token(user)

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    reset_url = f'{frontend_url}/auth/reset-password?token={plain_token}'

    context = {
        'first_name': user.first_name or user.username,
        'reset_url': reset_url,
        'expiry_minutes': TOKEN_EXPIRY_MINUTES,
        'year': timezone.now().year,
    }

    html_body = render_to_string('users/email/password_reset.html', context)
    text_body = (
        f'Hi {context["first_name"]},\n\n'
        f'We received a request to reset your Jehostarter password.\n\n'
        f'Click the link below to set a new password:\n\n'
        f'{reset_url}\n\n'
        f'This link expires in {TOKEN_EXPIRY_MINUTES} minutes.\n\n'
        f'If you did not request this, you can safely ignore this email.\n'
    )

    subject = 'Reset your Jehostarter password'
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    msg = EmailMultiAlternatives(subject, text_body, from_email, to_email)
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=False)

    backend = settings.EMAIL_BACKEND
    if 'console' in backend:
        logger.warning(
            'Password reset email for %s was printed to the console only. '
            'Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in backend/.env for real delivery.',
            user.email,
        )
    else:
        logger.info('Password reset email sent to %s via %s', user.email, backend)


def mark_token_used(token: str) -> None:
    """Mark a reset token as used after successful password reset."""
    token_hash = _hash_token(token.strip())
    PasswordResetToken.objects.filter(
        token_hash=token_hash,
    ).update(used_at=timezone.now())


def verify_reset_token(token: str):
    """
    Validate a reset token. Returns (user, error_message).
    On success, returns (user, None).
    """
    if not token:
        return None, 'Token is required.'

    token_hash = _hash_token(token.strip())

    record = (
        PasswordResetToken.objects
        .filter(token_hash=token_hash)
        .order_by('-created_at')
        .first()
    )

    if not record:
        return None, 'Invalid or expired reset link.'

    if record.is_used:
        return None, 'This reset link has already been used. Request a new one.'

    if record.is_expired:
        return None, 'This reset link has expired. Request a new one.'

    return record.user, None
