# Generated by Django 3.2.13 on 2022-06-27 14:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('label_domain', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='label',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
