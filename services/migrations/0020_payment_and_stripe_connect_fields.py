from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0019_alter_chaperoneservice_help_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicerequest',
            name='payment_id',
            field=models.CharField(blank=True, help_text='Payment ULID in payment service', max_length=26),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='payment_status',
            field=models.CharField(choices=[('unpaid', 'Unpaid'), ('authorized', 'Authorized Hold'), ('captured', 'Captured / Paid'), ('released', 'Released / Canceled'), ('refunded', 'Refunded')], default='unpaid', max_length=20),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='platform_fee',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='provider_payout',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='transfer_group',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='serviceproviderprofile',
            name='stripe_account_id',
            field=models.CharField(blank=True, help_text='Stripe Connect account ID (acct_...)', max_length=100),
        ),
        migrations.AddField(
            model_name='serviceproviderprofile',
            name='stripe_onboarding_completed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='serviceproviderprofile',
            name='stripe_charges_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='serviceproviderprofile',
            name='stripe_payouts_enabled',
            field=models.BooleanField(default=False),
        ),
    ]
