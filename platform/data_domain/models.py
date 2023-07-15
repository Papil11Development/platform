from uuid import uuid4

from django.db import models

from collector_domain.models import Camera
from user_domain.models import Workspace

bsm_indicator = "$"


class Activity(models.Model):
    class Type(models.IntegerChoices):
        PROGRESS = 1
        FINALIZED = 2
        FAILED = 3

    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)

    workspace = models.ForeignKey(Workspace, related_name='activities', on_delete=models.CASCADE, null=False)
    camera = models.ForeignKey(Camera, related_name='activities', on_delete=models.SET_NULL, null=True, blank=True)
    person = models.ForeignKey(to='person_domain.Person', related_name='activities', on_delete=models.CASCADE,
                               null=True, blank=True)

    data = models.JSONField(default=dict, null=True)
    status = models.IntegerField(choices=Type.choices, default=Type.PROGRESS)
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
