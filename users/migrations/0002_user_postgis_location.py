from django.db import migrations
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):
    """
    Replaces the old latitude/longitude DecimalFields with a single
    PostGIS PointField. Run AFTER enabling the postgis extension:
        psql -d yourdb -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    """

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # Remove old decimal fields if they exist (from previous migration)
        # Comment these out if you never ran the previous lat/lon migration
        # migrations.RemoveField(model_name='user', name='latitude'),
        # migrations.RemoveField(model_name='user', name='longitude'),

        migrations.AddField(
            model_name='user',
            name='location',
            field=django.contrib.gis.db.models.fields.PointField(
                blank=True, geography=True, null=True, srid=4326
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='location_source',
            field=django.contrib.gis.db.models.fields.CharField(
                blank=True,
                choices=[
                    ('gps',      'GPS'),
                    ('ip',       'IP Geolocation'),
                    ('timezone', 'Timezone Detection'),
                    ('manual',   'Manual Entry'),
                ],
                max_length=10,
            ),
        ),
    ]