from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0016_serviceproviderprofile_phone_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chaperoneservice',
            name='help_type',
            field=models.CharField(choices=[('arrival', 'Arrival'), ('housing', 'Housing'), ('administration', 'Administration'), ('employment', 'Employment'), ('settlement', 'Settlement'), ('appointments', 'Appointments'), ('transport', 'Transport'), ('education', 'Education'), ('digital', 'Digital'), ('shopping', 'Shopping'), ('communication', 'Communication'), ('community', 'Community'), ('local_orientation', 'Local Orientation'), ('moving', 'Moving'), ('family_settlement', 'Family Settlement'), ('business_setup', 'Business Setup'), ('general_errands', 'General Errands')], max_length=20),
        ),
    ]
