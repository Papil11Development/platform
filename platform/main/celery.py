import os
import re
from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
from main import settings
from platform_lib.types import ElasticAction


# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

app = Celery('main')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'trigger-handler': {
        'task': 'notification_domain.tasks.triggers_handler',
        'schedule': settings.TRIGGERS_HANDLER_PERIOD,
        'args': ()
    },
    'agent-status-checker': {
        'task': 'collector_domain.tasks.agent_status_checker',
        'schedule': settings.AGENT_STATUS_CHECK_PERIOD,
        'args': ()
    }
}


app.conf.task_routes = {
    'notification_domain.tasks.triggers_handler': {'queue': settings.NOTIFICATIONS_QUEUE},
    'notification_domain.tasks.send_notification_task': {'queue': settings.NOTIFICATION_SENDER_QUEUE},
    'collector_domain.tasks.*': {'queue': settings.COLLECTOR_QUEUE},
    re.compile(r'^data_domain\.tasks\.(?!elastic_(drop|push|manager)$)(.*)'): {
        'queue': settings.REIDENTIFICATION_QUEUE
    },
    'person_domain.tasks.duplicate_persons': {'queue': settings.QA_QUEUE},
}


if settings.ENABLE_ELK:
    app.conf.beat_schedule.update({
        'elastic-manager': {
            'task': 'data_domain.tasks.elastic_manager',
            'schedule': settings.PUSH_TO_ELASTIC_PERIOD,
            'args': (),
            'kwargs': {
                'action': ElasticAction.push
            }
        }
    })

    app.conf.task_routes.update({
        re.compile(r'^data_domain\.tasks.elastic_(drop|push)$'): {'queue': settings.ELASTIC_QUEUE},
        'data_domain.tasks.elastic_manager': {'queue': settings.ELASTIC_MANAGER_QUEUE},
        'user_domain.tasks.sign_up_kibana': {'queue': settings.SIGNUP_QUEUE},
    })


if not settings.IS_ON_PREMISE:
    app.conf.beat_schedule.update({
        'send_usage_records': {
            'task': 'licensing.tasks.send_usage_records',
            'schedule': crontab(minute=30, hour=23),
            'args': ()
        },
        'clean-deactivated-workspaces': {
            'task': 'data_domain.tasks.clean_deactivated_workspaces',
            'schedule': timedelta(minutes=10),
            'args': ()
        },
        'sample-retention-policy': {
            'task': 'data_domain.tasks.sample_retention_policy',
            'schedule': crontab(minute=0, hour=12, day_of_week=0)
        },
    })

    app.conf.task_routes.update({
        'data_domain.tasks.sample_retention_policy': {'queue': settings.DATA_PURGE_QUEUE},
        'data_domain.tasks.clean_deactivated_workspaces': {'queue': settings.DATA_PURGE_QUEUE},
        'licensing.tasks.*': {'queue': settings.LICENSING_QUEUE},
    })

app.conf.timezone = 'UTC'
