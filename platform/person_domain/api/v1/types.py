import datetime
from typing import List, Optional

import strawberry
from strawberry import ID

from person_domain import models
from label_domain.api.v1.types import ProfileGroupOutput
from data_domain.api.v1.types import ActivityType, SampleType
from platform_lib.managers import ActivityProcessManager
from platform_lib.types import JSONString
from platform_lib.utils import isoformat_time


@strawberry.input
class ProfileInput:
    """Input object required to create a profile."""
    profile_group_ids: Optional[List[Optional[ID]]] = strawberry.field(description='Profile group ids in list',
                                                                       default=None)
    info: Optional[JSONString] = strawberry.field(description='Profile information in JSON', default=None)


@strawberry.django.type(models.Profile)
class ProfileOutput:
    id: ID
    info: JSONString

    last_modified: datetime.datetime
    creation_date: datetime.datetime

    @strawberry.field
    def samples_objects(self) -> List[SampleType]:
        return self.samples.all()

    @strawberry.field
    def profile_groups(self) -> List[ProfileGroupOutput]:
        return self.profile_groups.all()

    @strawberry.field
    def person_id(self) -> ID:
        return self.person.id

    @strawberry.field
    def main_sample_id(self) -> Optional[str]:
        first_activity = self.person.activities.first()
        first_best_shot = ActivityProcessManager(first_activity.data).get_face_best_shot() if first_activity else None

        return self.info.get('main_sample_id', (first_best_shot or {}).get("id"))

    @strawberry.field
    def main_sample(self) -> Optional[List[SampleType]]:
        return [self.samples.get(id=self.info.get("main_sample_id"))]

    @strawberry.field
    def profile_group_ids(self) -> List[ID]:
        return [label.id for label in self.profile_groups.all()]


@strawberry.django.type(models.Person)
class PersonOutput:
    id: ID
    profile: ProfileOutput
    last_modified: datetime.datetime
    creation_date: datetime.datetime

    @strawberry.field
    def activities(self) -> Optional[List[ActivityType]]:
        return self.activities.all()

    @strawberry.field
    def activities_count(self) -> Optional[int]:
        return self.activities.count()

    @strawberry.field
    def first_activity_date(self) -> Optional[str]:
        if self.activities.exists():
            activity = self.activities.order_by('creation_date').first()
            time_point = ActivityProcessManager(activity.data).get_human_timeinterval()[0]
            return isoformat_time(time_point)
        else:
            return None

    @strawberry.field
    def last_activity_date(self) -> Optional[str]:
        if self.activities.exists():
            activity = self.activities.order_by('-creation_date').first()
            time_point = ActivityProcessManager(activity.data).get_human_timeinterval()[0]
            return isoformat_time(time_point)
        else:
            return None


@strawberry.type
class PersonsCollection:
    total_count: int
    collection_items: List[PersonOutput]


@strawberry.type
class ProfilesCollection:
    total_count: int
    collection_items: List[ProfileOutput]


@strawberry.type
class OkType:
    ok: Optional[bool]


@strawberry.type
class MergeOutput(OkType):
    target_person: PersonOutput


@strawberry.type
class ProfileCreateOutput(OkType):
    profile: ProfileOutput
    is_created: bool


@strawberry.type
class ProfileUpdateOutput(OkType):
    profile: ProfileOutput


person_map = {'sessionId': 'track_binds__session__id', 'providerId': 'provider_id', 'providerType': 'provider_type',
              'creationDate': 'creation_date', 'lastModified': 'last_modified'}

profile_map = {'personInfo': 'person_info', 'groupsIds': 'profile_groups__id__in', 'mainSampleId': 'main_sample_id',
               'creationDate': 'creation_date', 'lastModified': 'last_modified'}
