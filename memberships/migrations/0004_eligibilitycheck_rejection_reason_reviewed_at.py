from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('memberships', '0003_eligibilitycheck_eligibilitydocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='eligibilitycheck',
            name='rejection_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='eligibilitycheck',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
