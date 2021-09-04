import logging

from django.core.management import BaseCommand

from notification_domain.models import Notification

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        logger.info('Delete all notifications ...')
        try:
            num, _ = Notification.objects.all().delete()
        except Exception:
            logger.warning('Could not delete notifications in bulk.')
            logger.info('Try to delete one by one ...')
            num = 0
            for notification in Notification.objects.all().iterator():
                try:
                    notification.delete()
                    num += 1
                except Exception as exc:
                    logger.error(f'Could not delete notification: {notification.id}\n{exc}')
        logger.info(f'{num} notifications have been removed.')
