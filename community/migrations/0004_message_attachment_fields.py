from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('community', '0003_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to='community_attachments/'),
        ),
        migrations.AddField(
            model_name='message',
            name='attachment_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='message',
            name='attachment_type',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='message',
            name='attachment_size',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
