import datetime
from typing import Optional, List
from uuid import UUID

import strawberry
import strawberry_django
from strawberry import ID, auto
from strawberry.arguments import UNSET

from data_domain.managers import ActivityManager
from data_domain.models import Sample, Activity
from platform_lib.types import JSON, FilterLookupCustom
from django.apps import apps

from platform_lib.managers import ActivityProcessManager
from platform_lib.utils import get_collection, isoformat_time, from_dict_to_class, FilterByWorkspaceMixin

profile_model = apps.get_model('person_domain', 'Profile')
person_model = apps.get_model('person_domain', 'Person')


@strawberry_django.filters.filter(Activity)
class ActivityFilter:
    id: FilterLookupCustom[ID] = strawberry_django.field(default=UNSET, description="Filtering activities by ids")
    creation_date: FilterLookupCustom[datetime.datetime] = strawberry_django.field(
        default=UNSET,
        description="Filtering activities by creation date"
    )
    last_modified: FilterLookupCustom[datetime.datetime] = strawberry_django.field(
        default=UNSET,
        description="Filtering activities by date of last modification"
    )
    profile_id: Optional[UUID] = strawberry_django.field(
        default=UNSET,
        description="Filtering profile activities by profile id"
    )

    def filter_profile_id(self, queryset):
        if self.profile_id is None:
            return queryset
        else:
            return queryset.filter(person__profile__id=self.profile_id)


@strawberry_django.ordering.order(Activity)
class ActivityOrdering:
    id: auto
    creation_date: auto
    last_modified: auto


@strawberry_django.type(Activity, description="""
An Activity is an object that stores grouped information
about some completed processes associated with a Profile, Camera and/or Location
""")
class ActivityOutput(FilterByWorkspaceMixin):
    description_name = "activities"

    id: ID = strawberry.field(description="Activity ID")
    data: JSON = strawberry.field(description="A set of processes that occurred within the same Activity")
    creation_date: datetime.datetime = strawberry.field(
        description="Activity creation date in ISO 8601 format with time zone"
    )
    last_modified: datetime.datetime = strawberry.field(
        description="Activity creation date in ISO 8601 format with time zone"
    )

    @strawberry.field(description="ID of the Camera object that captured the Activity")
    def camera_id(root) -> ID:
        return root.camera.id

    @strawberry.field(description='Id of the best shot of any part of a person, depending on the subject'
                                  ' it is requested from. For example: best shot of the face, body, etc.')
    def best_shot_id(root) -> Optional[ID]:
        return (ActivityManager.get_best_shot_ids(root) or [None])[0]  # noqa

    @strawberry.field(description="ID of the Profile object associated with the Activity")
    def profile_id(root) -> Optional[ID]:
        try:
            return root.person.profile.id
        except AttributeError:
            return None

    @strawberry.field(description="ID of the Location object where the Activity occurred")
    def location_id(root) -> str:
        camera_id = root.camera.id
        camera = apps.get_model('collector_domain', 'Camera')
        camera_obj = camera.objects.filter(id=camera_id)
        location = camera_obj.first().locations.first() if camera_obj.exists() else None

        return getattr(location, 'id', None)

    @strawberry.field(description="Activity start time in ISO 8601 format with time zone")
    def time_start(root) -> str:
        timestamp = ActivityProcessManager(root.data).get_human_timeinterval()[0]
        return isoformat_time(timestamp)


@strawberry.type(description="""
A Sample is an object that stores the image of a person's face and/or
a corresponding biometric template that is used for face recognition
""")
class SampleOutput:
    id: ID = strawberry.field(description="Sample ID")

    creation_date: Optional[datetime.datetime] = strawberry.field(
        description="Sample creation date in ISO 8601 format with time zone", default=None
    )
    last_modified: Optional[datetime.datetime] = strawberry.field(
        description="Sample creation date in ISO 8601 format with time zone", default=None
    )

    @strawberry.field(description="Image, biometric template and/or detection result in the Sample format")
    def data(self) -> JSON:
        return self.meta


@strawberry.type
class RawSample:
    objects: JSON


@strawberry.type
class MatchResult:
    distance: float
    fa_r: float = strawberry.field(name="faR")
    fr_r: float = strawberry.field(name="frR")
    score: float


@strawberry.type
class ProfileOutputData:
    id: ID
    info: JSON

    last_modified: datetime.datetime = strawberry.field(description='Profile last modified date in ISO 8601 UTC format')
    creation_date: datetime.datetime = strawberry.field(description='Profile creation date in ISO 8601 UTC format')

    @strawberry.field(description="ID of the Person object associated with the profile")
    def person_id(self) -> ID:
        return self.person.id

    @strawberry.field(description="Main Sample object for profile")
    def main_sample(self) -> Optional[SampleOutput]:
        return self.samples.get(id=self.info.get("main_sample_id"))

    @strawberry.field(description="Avatar id for profile")
    def avatar(self) -> Optional[ID]:
        return self.info.get("avatar_id")


@strawberry.type
class PersonSearchResult:
    profile: Optional[ProfileOutputData]

    @strawberry.field
    def sample(root) -> SampleOutput:
        person_id = root.get('personId')

        main_sample_id = person_model.objects.get(id=person_id).info.get('main_sample_id')
        return Sample.objects.get(id=main_sample_id)

    @strawberry.field
    def profile(root) -> Optional[ProfileOutputData]:
        person_id = root.get('personId')
        return profile_model.objects.filter(person_id=person_id).first()

    @strawberry.field
    def match_result(root) -> MatchResult:
        result = root.get('matchResult')
        if result.get('faR') is not None:
            result['fa_r'] = result.pop('faR')
            result['fr_r'] = result.pop('frR')
        return MatchResult(**result)  # noqa


@strawberry.type
class SearchType:
    @strawberry.field
    def template(root) -> str:
        return root.get('template')

    @strawberry.field
    def search_result(root) -> List[PersonSearchResult]:
        return root.get('searchResult')


ActivityCollection = strawberry.type(get_collection(ActivityOutput, 'ActivityCollection'),
                                     description="Filtered activity collection and total activity count")
