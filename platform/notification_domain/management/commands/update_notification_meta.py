from django.core.management import BaseCommand
from django.db import transaction

from notification_domain.models import Notification
from random import randint


class Command(BaseCommand):
    def handle(self, *args, **options):
        # add type and current_count in location_overflow notifications
        with transaction.atomic():
            for notification in Notification.objects.select_for_update().filter(meta__type__isnull=True):
                notification.meta['type'] = 'location_overflow'
                if notification.meta.get('current_count') is None:
                    notification.meta['current_count'] = notification.meta.get('limit') + randint(1, 2)
                notification.save()
