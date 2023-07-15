# Generated by Django 3.2.15 on 2022-11-22 15:06

import django.contrib.postgres.fields
from django.db import migrations, models
import uuid
from main.settings import REQUIRED_PROFILE_FIELDS


def copy_person_info(apps, schema_editor):
    Workspace = apps.get_model('user_domain', 'Workspace')
    ProfileSettings = apps.get_model('person_domain', 'ProfileSettings')
    for ws in Workspace.objects.all():
        ProfileSettings.objects.create(workspace_id=ws.id, extra_fields=REQUIRED_PROFILE_FIELDS)


def rollback(apps, schema_editor):
    # doesn't make sense
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('person_domain', '0003_auto_20221014_1037'),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfileSettings",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("workspace_id", models.UUIDField(editable=False)),
                (
                    "extra_fields",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=100),
                        default=[],
                        size=None,
                    ),
                ),
                ("last_modified", models.DateTimeField(auto_now=True, null=True)),
                ("creation_date", models.DateTimeField(auto_now_add=True, null=True)),
            ],
            options={
                "verbose_name_plural": "ProfileSettings",
                "db_table": "profile_settings",
            },
        ),
        migrations.RunPython(copy_person_info, rollback),
    ]