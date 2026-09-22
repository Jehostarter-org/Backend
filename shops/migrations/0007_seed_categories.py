from django.db import migrations


DEFAULT_CATEGORIES = [
    ('Marketplace', 'marketplace', 'store'),
    ('Vehicles', 'vehicles', 'car'),
    ('Housing', 'housing', 'home'),
    ('Fashion', 'fashion', 'shirt'),
    ('Electronics', 'electronics', 'cpu'),
    ('Furniture', 'furniture', 'sofa'),
    ('Baby & Kids', 'baby-kids', 'baby'),
    ('Books', 'books', 'book'),
    ('Equipment & Tools', 'equipment-tools', 'wrench'),
    ('Other', 'other', 'boxes'),
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model('shops', 'Category')
    for name, slug, icon in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(slug=slug, defaults={'name': name, 'icon': icon})


def unseed_categories(apps, schema_editor):
    Category = apps.get_model('shops', 'Category')
    Category.objects.filter(slug__in=[slug for _, slug, _ in DEFAULT_CATEGORIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0006_shopapprovalrequest_shopdocument'),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
