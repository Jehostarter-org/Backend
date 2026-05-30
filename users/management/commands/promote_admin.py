from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Grant admin portal access to an existing user (sets is_staff=True).'

    def add_arguments(self, parser):
        parser.add_argument('identifier', help='Username or email of the user to promote')
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Also grant Django superuser permissions',
        )

    def handle(self, *args, **options):
        identifier = options['identifier'].strip()
        user = User.objects.filter(username__iexact=identifier).first()
        if user is None:
            user = User.objects.filter(email__iexact=identifier).first()

        if user is None:
            raise CommandError(f'No user found for "{identifier}".')

        user.is_staff = True
        if options['superuser']:
            user.is_superuser = True
        user.save(update_fields=['is_staff', 'is_superuser'] if options['superuser'] else ['is_staff'])

        self.stdout.write(self.style.SUCCESS(
            f'Promoted {user.username} ({user.email}) — is_staff=True'
            + (', is_superuser=True' if options['superuser'] else '')
        ))
        self.stdout.write('They can now sign in at /portal/login/')
