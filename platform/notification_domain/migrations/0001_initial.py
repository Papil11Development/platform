# Generated by Django 3.2.10 on 2021-12-10 08:43

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('user_domain', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Endpoint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('type', models.CharField(choices=[('EM', 'Email'), ('WH', 'Webhook'), ('BT', 'Bot')], max_length=2)),
                ('meta', models.JSONField(default=dict, null=True)),
                ('creation_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='endpoints', to='user_domain.workspace')),
            ],
            options={
                'verbose_name_plural': 'Endpoints',
                'db_table': 'notification_domain_endpoint',
            },
        ),
        migrations.CreateModel(
            name='Trigger',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('meta', models.JSONField(default=dict, null=True)),
                ('creation_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('endpoints', models.ManyToManyField(related_name='triggers', to='notification_domain.Endpoint')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='triggers', to='user_domain.workspace')),
            ],
            options={
                'verbose_name_plural': 'Triggers',
                'db_table': 'notification_domain_trigger',
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('meta', models.JSONField(default=dict)),
                ('creation_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('is_viewed', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='user_domain.workspace')),
            ],
            options={
                'verbose_name_plural': 'Notifications',
                'db_table': 'notification_domain_notification',
            },
        ),
    ]