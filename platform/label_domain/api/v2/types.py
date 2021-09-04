import datetime
import strawberry

from typing import List, Optional

from django.conf import settings
from strawberry import ID
from platform_lib.types import JSON, MutationResult
from platform_lib.utils import get_collection


@strawberry.input(description="Information needed to create a profile group")
class ProfileGroupInput:
    title: str = strawberry.field(description='Profile group title')
    info: Optional[JSON] = strawberry.field(description='Additional profile group info', default=None)


@strawberry.input(description="Information needed to update the profile group")
class ProfileGroupModifyInput(ProfileGroupInput):
    title: Optional[str] = strawberry.field(description='Profile group title', default=None)


@strawberry.type(description="Information about the profile group, e.g. name, linked profiles, etc.")
class ProfileGroupOutput:
    description_name = "profile groups"

    id: ID
    title: str = strawberry.field(description="Profile group title")
    info: JSON = strawberry.field(description="Profile group info")

    last_modified: datetime.datetime = strawberry.field(description="Last profile group modification date")
    creation_date: datetime.datetime = strawberry.field(description="Profile group creation date")

    @strawberry.field(description="Ids of linked profiles")
    def profile_ids(self, offset: int = 0, limit: int = settings.QUERY_LIMIT) -> Optional[List[ID]]:
        limit = min(limit, settings.QUERY_LIMIT)
        return self.profiles.values_list('id', flat=True)[offset:offset+limit]

    @strawberry.field(description="The object is in the archive")
    def archived(root) -> bool:
        return not root.is_active


@strawberry.type(description="Information about updated or created profile group")
class ProfileGroupModifyOutput(MutationResult):
    profile_group: Optional[ProfileGroupOutput] = strawberry.field(description="Updated or created profile group")


ProfileGroupsCollection = strawberry.type(get_collection(ProfileGroupOutput, 'ProfileGroupsCollection'),
                                          description="Filtered profile group collection and total profile group count")

label_map = {'creationDate': 'creation_date', 'lastModified': 'last_modified'}
