# Shops created before instant-activation should be sellable without admin review.

from django.db import migrations


def activate_shops(apps, schema_editor):
    Shop = apps.get_model('shops', 'Shop')
    Shop.objects.filter(is_active=False).exclude(
        approval_request__status='rejected',
    ).update(is_active=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0007_seed_categories'),
    ]

    operations = [
        migrations.RunPython(activate_shops, noop),
    ]
