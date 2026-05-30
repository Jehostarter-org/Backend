# Generated manually for email verification OTP

from django.conf import settings
from django.db import migrations, models
import users.models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_postgis_location'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailVerificationCode',
            fields=[
                ('id', models.CharField(default=users.models.generate_ulid, editable=False, max_length=26, primary_key=True, serialize=False)),
                ('code_hash', models.CharField(max_length=64)),
                ('expires_at', models.DateTimeField()),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('max_attempts', models.PositiveSmallIntegerField(default=5)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='email_verification_codes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'email_verification_codes',
                'ordering': ['-created_at'],
            },
        ),
    ]
