from typing import Union
from uuid import uuid4

from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import post_delete, pre_delete

from user_domain.models import Workspace
from collector_domain.models import Camera

bsm_indicator = "$"


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)

    workspace = models.ForeignKey(Workspace, related_name='activities', on_delete=models.CASCADE, null=False)
    camera = models.ForeignKey(Camera, related_name='activities', on_delete=models.SET_NULL, null=True, blank=True)
    person = models.ForeignKey(to='person_domain.Person', related_name='activities', on_delete=models.CASCADE,
                               null=True, blank=True)

    data = models.JSONField(default=dict, null=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'data_domain_activity'
        verbose_name_plural = 'Activities'


class Sample(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='samples', null=False)

    meta = models.JSONField(default=dict, null=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'data_domain_sample'
        verbose_name_plural = 'Samples'


class Blob(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
    data = models.BinaryField(editable=False, null=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'data_domain_blob'
        verbose_name_plural = 'Blobs'


class BlobMeta(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, related_name='blobmeta', on_delete=models.CASCADE, null=False)
    blob = models.OneToOneField(Blob, related_name='meta', on_delete=models.CASCADE, null=True)
    meta = models.JSONField(default=dict, null=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'data_domain_blobmeta'
        verbose_name_plural = 'BlobMeta'


# class SampleBlobMeta(models.Model):
#     id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
#     sample = models.ForeignKey(Sample, related_name='blobmeta_samples', on_delete=models.CASCADE)
#     blob_meta = models.ForeignKey(BlobMeta, related_name='blobmeta_samples', on_delete=models.CASCADE)
#
#     class Meta:
#         unique_together = ("sample", "blob_meta")
#
#
# class Dataset(models.Model):
#     id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
#     sample = models.ForeignKey(Sample, related_name='sample_labels', on_delete=models.CASCADE)
#     label = models.ForeignKey(Label, related_name='sample_labels', on_delete=models.CASCADE)
#
#     class Meta:
#         unique_together = ("sample", "label")


@receiver(post_delete, sender=BlobMeta)
def post_delete_blob_meta(sender, instance, *args, **kwargs):
    with transaction.atomic():
        if instance.blob:
            instance.blob.delete()


def delete_blobs(meta: Union[dict, list], key: str = '') -> Union[dict, list]:
    if key.startswith(bsm_indicator):
        try:
            BlobMeta.objects.get(id=meta['id']).delete()
        except (BlobMeta.DoesNotExist, TypeError) as exc:
            print(exc)
    elif isinstance(meta, dict):
        return {k: delete_blobs(v, k) for k, v in meta.items()}
    elif isinstance(meta, list):
        return [delete_blobs(m) for m in meta]


@receiver(pre_delete, sender=Sample)
def pre_delete_sample(sender, instance, *args, **kwargs):
    with transaction.atomic():
        delete_blobs(instance.meta)


@receiver(pre_delete, sender=Activity)
def pre_delete_activity(sender, instance, *args, **kwargs):
    with transaction.atomic():
        delete_blobs(instance.data)
