import uuid

from django.db import models

from user_domain.models import Workspace
from platform_lib.utils import ModelMixin


class Label(models.Model, ModelMixin):
    LOCATION = 'LO'
    PROFILE_GROUP = 'PG'
    AREA_TYPE = 'AT'
    TYPES = [
        (LOCATION, 'Location'),
        (PROFILE_GROUP, 'Profile Group'),
        (AREA_TYPE, 'Area Type')
    ]

    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=2, choices=TYPES)
    title = models.CharField(max_length=500)
    info = models.JSONField(default=dict)

    is_active = models.BooleanField(default=True)

    workspace = models.ForeignKey(Workspace, related_name='labels', on_delete=models.CASCADE)

    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    objects = ModelMixin.Manager()

    original_objects = models.Manager()

    def delete(self, *args, **kwargs):
        return ModelMixin.delete(self, *args, **kwargs)

    class Meta:
        db_table = 'label_domain_label'
        verbose_name_plural = 'Labels'
