import datetime
from typing import List, Optional

import strawberry
from strawberry import auto

from label_domain import models
from platform_lib.types import JSONString
from platform_lib.utils import get_collection


@strawberry.input
class ProfileGroupInput:
    """Input object required to create a profile group."""
    info: Optional[JSONString] = strawberry.field(description='Additional profile group info', default=None)
    title: str = strawberry.field(description='Profile group title', default='')


@strawberry.input
class LocationInput:
    """Input object required to create a location."""
    info: Optional[JSONString] = strawberry.field(description='Additional location info', default=None)
    extra: Optional[JSONString] = strawberry.field(description='Additional location info', default="{}")
    # title: Optional[str] = strawberry.field(description='Location title', default='')


@strawberry.input
class AreaTypeInput:
    """Input object required to create a area type."""
    info: Optional[JSONString] = strawberry.field(description='Additional area type info', default=None)
    title: str = strawberry.field(description='Area type title', default='')


@strawberry.type
class LabelProfile:
    id: Optional[strawberry.ID]
    last_modified: datetime.datetime


@strawberry.django.type(models.Label)
class ProfileGroupOutput:
    id: auto
    title: auto
    info: JSONString

    # profiles: List[ProfileType]

    last_modified: auto
    creation_date: auto

    @strawberry.field
    def profiles(self) -> Optional[List[LabelProfile]]:
        return [profile for profile in self.profiles.all()]


@strawberry.type
class OkType:
    ok: bool


@strawberry.type
class LocationOutput:

    @staticmethod
    def resolve_cameras_ids(root, info):
        try:
            return [camera.id for camera in root.cameras.all()]
        except Exception as ex:
            print(ex)
            return root.camerasIds

    id: strawberry.ID
    title: str
    info: Optional[JSONString]

    cameras_ids: Optional[List[strawberry.ID]] = strawberry.field(resolver=resolve_cameras_ids)

    # cameras: List[CameraOutput]

    last_modified: datetime.datetime
    creation_date: datetime.datetime


@strawberry.django.type(models.Label)
class AreaTypeOutput:
    id: auto
    title: auto
    info: JSONString

    # attention_areas: List[AttentionAreaOutput]

    last_modified: auto
    creation_date: auto


@strawberry.django.type(models.Label)
class LocationModifyOutput:
    ok: Optional[bool]
    location: Optional[LocationOutput]


AreaTypesCollection = strawberry.type(get_collection(AreaTypeOutput, 'AreaTypesCollection'))
LocationsCollection = strawberry.type(get_collection(LocationOutput, 'LocationsCollection'))
ProfileGroupsCollection = strawberry.type(get_collection(ProfileGroupOutput, 'ProfileGroupsCollection'))


label_map = {
    'creationDate': 'creation_date',
    'lastModified': 'last_modified'
}
