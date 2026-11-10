import django.db.models.deletion
import shops.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0009_shoplisting_subcategory'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='shop',
            name='stripe_account_id',
            field=models.CharField(blank=True, help_text='Stripe Connect account ID', max_length=100),
        ),
        migrations.AddField(
            model_name='shop',
            name='stripe_onboarding_completed',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.CharField(default=shops.models.generate_ulid, editable=False, max_length=26, primary_key=True, serialize=False)),
                ('total_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='USD', max_length=3)),
                ('payment_type', models.CharField(choices=[('full', 'Full Payment'), ('installment', 'Installment Payment')], default='installment', max_length=15)),
                ('status', models.CharField(choices=[('pending', 'Pending Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('in_fulfillment', 'In Fulfillment'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('stripe_customer_id', models.CharField(blank=True, max_length=100)),
                ('stripe_payment_method_id', models.CharField(blank=True, max_length=100)),
                ('transfer_group', models.CharField(blank=True, max_length=100)),
                ('rejection_reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('buyer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shop_orders', to=settings.AUTH_USER_MODEL)),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='shops.shoplisting')),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='shops.shop')),
            ],
            options={
                'db_table': 'shop_orders',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='InstallmentSchedule',
            fields=[
                ('id', models.CharField(default=shops.models.generate_ulid, editable=False, max_length=26, primary_key=True, serialize=False)),
                ('installment_number', models.PositiveSmallIntegerField(default=1)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('platform_fee_amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('seller_amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('due_date', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('authorized', 'Authorized'), ('paid', 'Paid'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='pending', max_length=20)),
                ('payment_id', models.CharField(blank=True, max_length=26)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='installments', to='shops.order')),
            ],
            options={
                'db_table': 'installment_schedules',
                'ordering': ['installment_number'],
            },
        ),
    ]
