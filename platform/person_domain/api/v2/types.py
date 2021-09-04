import datetime
import operator
import strawberry
from typing import Optional, List

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from strawberry import ID
from data_domain.api.v2.types import SampleOutput, ActivityOutput
from platform_lib.managers import ActivityProcessManager
from label_domain.api.v2.types import ProfileGroupOutput
from platform_lib.types import JSON, MutationResult
from platform_lib.utils import get_collection, isoformat_time


@strawberry.type(description="Object that represents a detected person"
                             " and contains all the information about that person")
class ProfileOutput:
    description_name = "profiles"

    id: ID

    last_modified: datetime.datetime = strawberry.field(description="Last profile modification date")
    creation_date: datetime.datetime = strawberry.field(description="Profile creation date")

    @strawberry.field(description="Info about human")
    def info(self) -> JSON:
        return self.info

    @strawberry.field(description="Objects that stored processed info about human blobs.")
    def samples(self, offset: int = 0, limit: int = settings.QUERY_LIMIT) -> Optional[List[SampleOutput]]:
        limit = min(limit, settings.QUERY_LIMIT)
        return self.samples.all()[offset:offset+limit]

    @strawberry.field(description="Groups the profile belongs to")
    def profile_groups(self, offset: int = 0, limit: int = settings.QUERY_LIMIT) -> Optional[List[ProfileGroupOutput]]:
        limit = min(limit, settings.QUERY_LIMIT)
        pg = self._prefetched_objects_cache[self.profile_groups.prefetch_cache_name]
        return pg[offset:offset+limit]

    @strawberry.field(description="Best human photo")
    def main_sample(self) -> Optional[SampleOutput]:
        samples = self._prefetched_objects_cache[self.samples.prefetch_cache_name]
        main_sample = next(filter(lambda sample: str(sample.id) == self.info.get("main_sample_id"), samples), None)
        return main_sample

    @strawberry.field(description="Human's photo")
    def avatar(self) -> Optional[ID]:
        return self.info.get("avatar_id")

    @strawberry.field(description="All human activities")
    def activities(self, offset: int = 0, limit: int = settings.QUERY_LIMIT) -> Optional[List[ActivityOutput]]:
        if self.person:
            limit = min(limit, settings.QUERY_LIMIT)
            return self.person.activities.all()[offset:offset+limit]

    @strawberry.field(description="Count of all human activity")
    def activities_count(self) -> Optional[int]:
        if self.person:
            return self.person.activities.count()

    @strawberry.field(description="Date of first human activity")
    def first_activity_date(self) -> Optional[str]:
        if self.person and self.person.activities.exists():
            activity = self.person.activities.first()
            timestamp = ActivityProcessManager(activity.data).get_human_timeinterval()[0]
            return isoformat_time(timestamp)

    @strawberry.field(description="Date of last human activity")
    def last_activity_date(self) -> Optional[str]:
        if self.person and self.person.activities.exists():
            last_activity = sorted(self.person.activities.all(), key=operator.attrgetter('creation_date'))[-1]
            timestamp = ActivityProcessManager(last_activity.data).get_human_timeinterval()[0]
            return isoformat_time(timestamp)


@strawberry.input(description="Information needed for profile creation")
class ProfileInput:
    profile_group_ids: Optional[List[Optional[ID]]] = strawberry.field(description='Profile group ids',
                                                                       default=None)
    info: Optional[JSON] = strawberry.field(description='Profile information in JSON', default=None)


@strawberry.type(description="Information about created or an existing profile"
                             " if the person in the photo has already been captured by agent")
class ProfileCreateOutput(MutationResult):
    profile: ProfileOutput = strawberry.field(description="Created or linked profile")
    is_created: bool = strawberry.field(description=("Determines if a new profile has been created"
                                                     " or if the photo has been linked to an existing profile"))


@strawberry.type(description="Information about updated profile")
class ProfileUpdateOutput(MutationResult):
    profile: ProfileOutput = strawberry.field(description="Updated profile object")


@strawberry.type(description="Information about bulk updated profiles")
class ProfilesUpdateOutput(MutationResult):
    profiles: List[ProfileOutput] = strawberry.field(description="Updated profiles")


ProfilesCollection = strawberry.type(get_collection(ProfileOutput, "ProfilesCollection"),
                                     description="Filtered profiles collection and total profiles count")


profile_map = {'personInfo': 'person_info', 'groupsIds': 'profile_groups__id__in', 'mainSampleId': 'main_sample_id',
               'avatarId': 'avatar_id', 'creationDate': 'creation_date', 'lastModified': 'last_modified'}
