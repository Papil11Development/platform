import uuid

from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import pre_delete

from label_domain.models import Label
from user_domain.models import Workspace
from platform_lib.utils import ModelMixin, utcnow_with_tz


class Agent(models.Model, ModelMixin):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)

    workspace = models.ForeignKey(Workspace, related_name='agents', on_delete=models.CASCADE, null=False)
    info = models.JSONField(default=dict, null=True)
    # profile_groups = models.ManyToManyField(ProfileGroup, related_name='devices', blank=True)

    is_active = models.BooleanField(default=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    objects = ModelMixin.Manager()

    original_objects = models.Manager()

    def delete(self, *args, **kwargs):
        return ModelMixin.delete(self, *args, **kwargs)

    class Meta:
        db_table = 'collector_domain_agent'
        verbose_name = 'Agent'


class Camera(models.Model, ModelMixin):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=500, default='')
    agent = models.ForeignKey(Agent, related_name='cameras', on_delete=models.CASCADE, null=False)
    workspace = models.ForeignKey(Workspace, related_name='cameras', on_delete=models.CASCADE, null=False)
    locations = models.ManyToManyField(Label, related_name="cameras", through="Location")

    is_active = models.BooleanField(default=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    objects = ModelMixin.Manager()

    original_objects = models.Manager()

    def delete(self, *args, **kwargs):
        return ModelMixin.delete(self, *args, **kwargs)

    class Meta:
        db_table = 'collector_domain_camera'
        verbose_name = 'Camera'


class AttentionArea(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)

    info = models.JSONField(default=dict, null=True)
    workspace = models.ForeignKey(Workspace, related_name='attention_areas', on_delete=models.CASCADE, null=False)
    camera = models.ForeignKey(Camera, related_name='attention_areas', on_delete=models.CASCADE, null=False)
    area_types = models.ManyToManyField(Label, related_name="attention_areas", through="AreaType")

    is_active = models.BooleanField(default=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    objects = ModelMixin.Manager()

    original_objects = models.Manager()

    class Meta:
        db_table = 'collector_domain_attention_area'
        verbose_name = 'Attention area'


class AreaType(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)

    attention_area = models.ForeignKey(AttentionArea, related_name='area_type', on_delete=models.CASCADE, null=False)
    label = models.ForeignKey(Label, related_name='area_type', on_delete=models.CASCADE, null=False)

    class Meta:
        unique_together = ("attention_area", "label")


class Location(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)

    camera = models.ForeignKey(Camera, related_name='camera_location', on_delete=models.CASCADE, null=False)
    label = models.ForeignKey(Label, related_name='camera_location', on_delete=models.CASCADE, null=False)

    class Meta:
        unique_together = ("camera", "label")


class AgentIndexEvent(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=30)  # del
    workspace_id = models.UUIDField()
    profile_id = models.UUIDField()
    person_id = models.UUIDField()
    data = models.JSONField(default=dict)
    creation_date = models.DateTimeField(default=utcnow_with_tz)

    class Meta:
        indexes = [
            models.Index(fields=['creation_date'])
        ]


@receiver(pre_delete, sender=Agent)
def pre_delete_cameras(sender, instance, *args, **kwargs):
    with transaction.atomic():
        cameras = instance.cameras.all()
        cameras.delete()
