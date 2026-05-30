"""
Send a test verification email to confirm SMTP settings.

Usage:
  python manage.py test_verification_email user@example.com
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from users.email_verification import send_verification_email

User = get_user_model()


class Command(BaseCommand):
    help = 'Send a test OTP verification email to the given address (or existing user).'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Recipient email address')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).order_by('-date_joined').first()

        if not user:
            raise CommandError(f'No user found with email {email}. Register first or use an existing account.')

        from django.conf import settings
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f'Using EMAIL_BACKEND: {backend}')
        self.stdout.write(f'From: {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'To: {user.email}')

        try:
            send_verification_email(user)
        except Exception as exc:
            raise CommandError(f'Failed to send: {exc}') from exc

        self.stdout.write(self.style.SUCCESS('Verification email sent successfully.'))
