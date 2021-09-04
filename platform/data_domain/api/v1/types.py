from typing import TypeVar, List, Optional
from operator import attrgetter

import strawberry
from django.conf import settings
from strawberry import ID, auto

from data_domain import models
from data_domain.managers import OngoingManager, SampleManager

from platform_lib.managers import ActivityProcessManager
from platform_lib.types import JSON, JSONString, CustomBinaryType
from django.apps import apps

from platform_lib.utils import get_collection, isoformat_time

DjangoModelType = TypeVar('DjangoModelType', models.Activity, models.Sample, models.Blob, models.BlobMeta)


def resolve_relation(root: DjangoModelType, attr: str):
    """
    :root - django model
    :attr - chain of fields

    Return field of complex chain relation.
    Example: resolve_relation(sample, 'profile.person.id') -> sample.profile.person.id
    """
    try:
        return attrgetter(attr)(root)
    except AttributeError:
        return None


def resolve_camera_id(root):
    return resolve_relation(root, 'camera.id')


def resolve_person_id(root):
    return resolve_relation(root, 'person.id')


def resolve_profile_id(root):
    return resolve_relation(root, 'profile.id')


def resolve_blob_id(root):
    return resolve_relation(root, 'blob.id')


def resolve_location_id(root):
    camera_id = resolve_camera_id(root)
    camera = apps.get_model('collector_domain', 'Camera')
    camera_obj = camera.objects.filter(id=camera_id)
    location = camera_obj.first().locations.first() if camera_obj.exists() else None
    if location is not None:
        return location.id
    else:
        return ''


@strawberry.type
class ActivityProfileType:
    id: ID

    @strawberry.field()
    def main_sample_id(self) -> Optional[str]:
        return self.info.get('main_sample_id')


@strawberry.type
class ActivityPersonType:
    id: ID
    profile: Optional[ActivityProfileType]


@strawberry.django.type(models.Activity)
class ActivityType:

    id: auto
    camera_id: ID = strawberry.field(resolver=resolve_camera_id)
    person_id: ID = strawberry.field(resolver=resolve_person_id)
    person: Optional[ActivityPersonType]
    location_id: str = strawberry.field(resolver=resolve_location_id)
    data: JSON
    creation_date: auto
    last_modified: auto

    @strawberry.field
    def time_start(self) -> str:
        time_point = ActivityProcessManager(self.data).get_human_timeinterval()[0]
        return isoformat_time(time_point)


@strawberry.type
class ActivityCollection:
    total_count: int
    collection_items: List[ActivityType]


@strawberry.django.type(models.Blob)
class BlobType:
    id: auto
    creation_date: auto
    last_modified: auto


@strawberry.django.type(models.BlobMeta)
class BlobMetaType:
    id: auto
    blob: BlobType
    meta: JSONString
    creation_date: auto
    last_modified: auto

    @strawberry.field
    def type(self) -> Optional[str]:
        return self.meta.get('type', '')

    @strawberry.field
    def binary_data(self) -> Optional[CustomBinaryType]:
        return self.blob.data


@strawberry.django.type(models.Sample)
class SampleType:
    id: auto
    creation_date: auto
    last_modified: auto

    @strawberry.field
    def data(self) -> JSON:
        return self.meta

    @strawberry.field(description="ID of profile that was captured on sample")
    def profile_id(self) -> Optional[ID]:
        return self.profile.first().id if self.profile.first() else None

    @strawberry.field(description="Template associated with sample")
    def template(self) -> Optional[BlobMetaType]:
        template_version = self.workspace.config.get('template_version', settings.DEFAULT_TEMPLATES_VERSION)
        template_id = SampleManager.get_template_id(self.meta, template_version)
        return models.BlobMeta.objects.get(id=template_id)


StrawberryModelType = TypeVar('StrawberryModelType', ActivityType, SampleType)


@strawberry.type
class OngoingRoi:
    @staticmethod
    def resolve_camera_roi_id(root):
        return root.get('camera_roi_id')

    @staticmethod
    def resolve_title(root):
        return root.get('title')

    camera_roi_id: Optional[ID] = strawberry.field(resolver=resolve_camera_roi_id)
    title: Optional[str] = strawberry.field(resolver=resolve_title)


@strawberry.type
class OngoingProfileGroup:
    @staticmethod
    def resolve_id(root):
        return root.get('id')

    @staticmethod
    def resolve_title(root):
        return root.get('title')

    id: Optional[ID] = strawberry.field(resolver=resolve_id)
    title: Optional[str] = strawberry.field(resolver=resolve_title)


@strawberry.type
class OngoingOutput:
    @staticmethod
    def resolve_id(root, info):
        parent = OngoingManager.get_parent_process(root)
        return parent.get('id', '')

    @staticmethod
    def resolve_data(root, info):
        return root

    @staticmethod
    def resolve_location_id(root, info):
        return root.get('location_id', '')

    @staticmethod
    def resolve_rois(root, info):
        return root.get('rois', [])

    @staticmethod
    def resolve_camera_id(root, info):
        return root.get('camera_id', '')

    @staticmethod
    def resolve_profile_groups(root, info):
        parent = OngoingManager.get_parent_process(root)
        return parent.get('object', {}).get('match_data', {}).get('profileGroups', [])

    id: ID = strawberry.field(resolver=resolve_id)
    data: Optional[JSONString] = strawberry.field(resolver=resolve_data)
    location_id: Optional[ID] = strawberry.field(resolver=resolve_location_id)
    person_id: Optional[ID] = strawberry.field(resolver=resolve_person_id)
    rois: Optional[List[OngoingRoi]] = strawberry.field(resolver=resolve_rois)
    camera_id: Optional[ID] = strawberry.field(resolver=resolve_camera_id)
    profile_groups: Optional[List[OngoingProfileGroup]] = strawberry.field(resolver=resolve_profile_groups)


OngoingsCollection = strawberry.type(get_collection(OngoingOutput, 'OngoingsCollection'))

activity_map = {'creationDate': 'creation_date'}
