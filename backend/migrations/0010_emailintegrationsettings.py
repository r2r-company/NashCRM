# Generated by Django 5.2.3 on 2025-06-16 15:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0009_remove_lead_actual_cash'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailIntegrationSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='default', max_length=100, unique=True)),
                ('email', models.EmailField(max_length=254, verbose_name='Логін до пошти')),
                ('app_password', models.CharField(max_length=100, verbose_name='App Password')),
                ('imap_host', models.CharField(default='imap.gmail.com', max_length=100)),
                ('folder', models.CharField(default='INBOX', max_length=50)),
                ('allowed_sender', models.EmailField(max_length=254, verbose_name='Дозволений відправник')),
                ('allowed_subject_keyword', models.CharField(blank=True, max_length=100, verbose_name='Ключове слово в темі')),
            ],
            options={
                'verbose_name': 'Налаштування Email',
                'verbose_name_plural': 'Налаштування Email',
            },
        ),
    ]
