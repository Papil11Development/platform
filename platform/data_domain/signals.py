from typing import Union, Optional, List

from django.db import transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from data_domain.managers import ActivityManager, SampleManager
from data_domain.models import BlobMeta, Activity, bsm_indicator, Sample
from platform_lib.managers import ActivityProcessManager


@receiver(post_delete, sender=BlobMeta)
def post_delete_blob_meta(sender, instance, *args, **kwargs):
    with transaction.atomic():
        if instance.blob:
            instance.blob.delete()


def delete_blobs(meta: Union[dict, list], exclude_ids: Optional[List[str]] = None):
    if isinstance(meta, dict):
        for key, value in meta.items():
            if value is not None:
                if key.startswith(bsm_indicator) and value['id'] not in (exclude_ids or []):
                    try:
                        BlobMeta.objects.get(id=value['id']).delete()
                    except BlobMeta.DoesNotExist as ex:
                        print(f'Exception: {ex} BlobId: {value["id"]}')
                else:
                    delete_blobs(value, exclude_ids)
    elif isinstance(meta, list):
        for item in meta:
            delete_blobs(item, exclude_ids)


@receiver(pre_delete, sender=Sample)
def pre_delete_sample(sender, instance, *args, **kwargs):
    with transaction.atomic():
        delete_blobs(instance.meta)


@receiver(pre_delete, sender=Activity)
def pre_delete_activity(sender, instance, *args, **kwargs):
    sample_ids = ActivityManager.get_samples_ids(instance)
    exclude_blobs = []

    samples = SampleManager.get_samples(sample_ids=sample_ids, workspace_id=str(instance.workspace_id))

    for sample in samples:
        if sample.meta:
            exclude_blobs += ActivityProcessManager._get_blob_ids(sample.meta)

    with transaction.atomic():
        delete_blobs(instance.data, exclude_ids=exclude_blobs)
