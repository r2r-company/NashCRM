# Generated by Django 5.2.3 on 2025-06-16 18:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0014_lead_status_updated_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lead',
            name='status_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
