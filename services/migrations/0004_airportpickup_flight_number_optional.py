# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0003_migrationspecialistapplication_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='airportpickup',
            name='flight_number',
            field=models.CharField(max_length=20, default='', blank=True),
        ),
    ]
