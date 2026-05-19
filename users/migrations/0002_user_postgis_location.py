from django.db import migrations, models
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
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
            field=models.CharField(
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