from datetime import timedelta

from django.core.management import BaseCommand
from django.db import transaction

from notification_domain.models import Notification
from data_domain.models import Activity
from platform_lib.managers import ActivityProcessManager


class Command(BaseCommand):
    def handle(self, *args, **options):
        # add activity_id, realtime_face_photo_id, realtime_body_photo_id in presence notifications
        with transaction.atomic():
            for notification in Notification.objects.select_for_update().filter(meta__type='presence'):
                person_activity = Activity.objects.filter(person__id=notification.meta['person_id'],
                                                          creation_date__lt=notification.creation_date + timedelta(
                                                              seconds=20)).order_by('creation_date').last()

                activity_data_manager = ActivityProcessManager(person_activity.data)
                try:
                    activity_id = str(person_activity.id)
                    face_best_shot = activity_data_manager.get_face_best_shot()
                    body_best_shot = activity_data_manager.get_body_best_shot()

                    face_blob_id = face_best_shot.get("id")
                    body_blob_id = body_best_shot.get("id")
                except AttributeError:
                    activity_id = None
                    face_blob_id = None
                    body_blob_id = None

                notification.meta.update({
                    'activity_id': activity_id,
                    'realtime_face_photo_id': face_blob_id,
                    'realtime_body_photo_id': body_blob_id,
                })
                notification.save()
