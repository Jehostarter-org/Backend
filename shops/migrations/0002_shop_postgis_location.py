from django.db import migrations
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):
    """
    Replaces old latitude/longitude DecimalFields on Shop with a PointField.
    Run AFTER: psql -d yourdb -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    """

    dependencies = [
        ('shops', '0001_initial'),
    ]

    operations = [
        # Remove old decimal fields if they existed
        # migrations.RemoveField(model_name='shop', name='latitude'),
        # migrations.RemoveField(model_name='shop', name='longitude'),

        migrations.AddField(
            model_name='shop',
            name='location',
            field=django.contrib.gis.db.models.fields.PointField(
                blank=True, geography=True, null=True, srid=4326
            ),
        ),
    ]