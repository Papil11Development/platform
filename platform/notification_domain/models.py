import copy
import uuid

from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import pre_delete

from platform_lib.exceptions import InvalidTriggerMetaJson
from platform_lib.managers import TriggerMetaManager
from platform_lib.meta_language_parser import MetaLanguageParser
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import trigger_meta_scheme
from platform_lib.utils import ModelMixin
from user_domain.models import Workspace
from django.utils.translation import gettext_lazy as _


class Endpoint(models.Model, ModelMixin):
    class Type(models.TextChoices):
        WEB_INTERFACE = 'WI', _('Web interface')
        EMAIL = 'EM', _('Email')
        WEBHOOK = 'WH', _('Webhook')
        BOT = 'BT', _('Bot')

    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=2, choices=Type.choices)
    meta = models.JSONField(default=dict, null=True)
    workspace = models.ForeignKey(Workspace, related_name='endpoints', on_delete=models.CASCADE, null=False)
    is_active = models.BooleanField(default=True)

    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    objects = ModelMixin.Manager()

    original_objects = models.Manager()

    class Meta:
        db_table = 'notification_domain_endpoint'
        verbose_name_plural = 'Endpoints'

    def delete(self, *args, **kwargs):
        return ModelMixin.delete(self, *args, **kwargs)


class Trigger(models.Model, ModelMixin):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500, default='')
    meta = models.JSONField(default=dict, null=True)
    __original_meta = None

    workspace = models.ForeignKey(Workspace, related_name='triggers', on_delete=models.CASCADE, null=False)
    endpoints = models.ManyToManyField(Endpoint, related_name='triggers')

    is_active = models.BooleanField(default=True)

    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    objects = ModelMixin.Manager()

    original_objects = models.Manager()

    class Meta:
        db_table = 'notification_domain_trigger'
        verbose_name_plural = 'Triggers'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_meta = copy.deepcopy(self.meta)

    def save(self, *args, **kwargs):

        if self._state.adding or self.meta != self.__original_meta:
            if not is_valid_json(self.meta, trigger_meta_scheme):
                raise InvalidTriggerMetaJson

        self.__original_meta = self.meta
        super(Trigger, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return ModelMixin.delete(self, *args, **kwargs)


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, related_name='notifications', on_delete=models.CASCADE, null=False)
    meta = models.JSONField(default=dict)

    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    is_viewed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'notification_domain_notification'
        verbose_name_plural = 'Notifications'


@receiver(pre_delete, sender="notification_domain.Trigger")
def deactivate_notification_trigger(sender, instance, *args, **kwargs):
    trigger_id = str(instance.id)
    with transaction.atomic():
        Notification.objects.select_for_update().filter(meta__trigger_id=trigger_id).update(is_active=False)


@receiver(pre_delete, sender="label_domain.Label")
def pre_delete_label(sender, instance, *args, **kwargs):
    # TODO [NOTIF] move to manager resolve circular imports
    with transaction.atomic():
        workspace_triggers = Trigger.objects.filter(workspace_id=instance.workspace_id).values_list('id', 'meta')

        target_trigger_ids = {
            str(trigger[0]) for trigger in workspace_triggers
            if MetaLanguageParser(TriggerMetaManager(trigger[1]).get_condition_language()).is_have_target(instance.id)
        }

        Trigger.objects.filter(id__in=target_trigger_ids).delete()


@receiver(pre_delete, sender="label_domain.Label")
def delete_trigger_location(sender, instance, *args, **kwargs):
    location_id = str(instance.id)
    triggers = Trigger.objects.filter(meta__location_id=location_id)
    notifications = Notification.objects.filter(meta__location_id=location_id)
    with transaction.atomic():
        triggers.delete()
        notifications.delete()


# TODO uncomment when location_overflow notification will work properly
# @receiver(post_save, sender="notification_domain.Notification")
# def send_notification_to_endpoints(sender, instance, created, *args, **kwargs):
#     send_notification_task = celery.app.signature('notification_domain.tasks.send_notification_task')
#
#     def send_notification(workspace_id: str,
#                           notification_id: str,
#                           notification_info: dict,
#                           trigger: Trigger):
#         for endpoint in trigger.endpoints.all():
#             message_data = NotificationMessageGenerator.get_message_data(endpoint.get_type_display(),
#                                                                          notification_info)
#
#             send_notification_task.delay(notification_id,
#                                          workspace_id,
#                                          endpoint_id=str(endpoint.id),
#                                          endpoint_type=endpoint.get_type_display(),
#                                          endpoint_meta=endpoint.meta,
#                                          message_data=message_data)
#     if created:
#         print("created")
#         trigger = Trigger.objects.get(id=instance.meta["trigger_id"])
#
#         send_notification(str(instance.workspace_id), str(instance.id), instance.meta, trigger)
