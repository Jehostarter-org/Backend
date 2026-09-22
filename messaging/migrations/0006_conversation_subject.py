# Generated manually for the support thread subject field.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0005_alter_messageattachment_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='subject',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
