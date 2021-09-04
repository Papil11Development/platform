from datetime import timedelta
from typing import List, Optional
import strawberry
from django.apps import apps
from strawberry import ID, auto

from notification_domain import models
from platform_lib.managers import TriggerMetaManager
from platform_lib.meta_language_parser import MetaLanguageParser
from platform_lib.types import JSONString, MutationResult
from platform_lib.utils import get_collection


@strawberry.input
class EndpointInput:
    """Input object required to create a endpoint."""
    meta: Optional[JSONString] = strawberry.field(description='Additional endpoint info', default=None)
    type: str = strawberry.field(description='Endpoint type', default=None)


@strawberry.input
class TriggerNewInput:
    """Input object required to create a trigger."""
    places: Optional[List[JSONString]] = strawberry.field(description='List of trigger places', default_factory=list)
    targets: Optional[List[JSONString]] = strawberry.field(description='List of trigger targets', default_factory=list)
    operation: Optional[str] = strawberry.field(description='Operation of comparison', default='>')
    limit: Optional[int] = strawberry.field(description='The limit of the acceptable value', default=0)
    endpoints: Optional[List[str]] = strawberry.field(description='Endpoints where the notification '
                                                                  'will be sent if the trigger condition is met',
                                                      default=None)


@strawberry.input
class TriggerInput:
    """Input object required to create a trigger for old front."""
    title: str = strawberry.field(description='Trigger title')
    location_id: str = strawberry.field(description='Where the trigger will be checked')
    lifetime: int = strawberry.field(description='Retention time of generated notification')
    limit: int = strawberry.field(description='Trigger execution condition')


@strawberry.django.type(models.Endpoint)
class EndpointOutput:
    id: auto
    type: auto
    meta: JSONString

    last_modified: auto
    creation_date: auto


@strawberry.django.type(models.Trigger)
class TriggerNewOutput:
    id: auto
    meta: JSONString
    endpoints: List[EndpointOutput]

    last_modified: auto
    creation_date: auto


@strawberry.type
class TriggerOutput:
    @staticmethod
    def resolve_lifetime(root, info) -> int:
        # It is sewn in the frontend code, therefore it always comes
        return TriggerMetaManager(root.meta).get_trigger_lifetime()

    @staticmethod
    def resolve_limit(root, info) -> int:
        parser = MetaLanguageParser(TriggerMetaManager(root.meta).get_condition_language())
        # Get target limit from first trigger condition variable
        return parser.get_variable_kwargs_by_number(0).get('target_limit')

    @staticmethod
    def resolve_location(root, info) -> str:
        parser = MetaLanguageParser(TriggerMetaManager(root.meta).get_condition_language())
        # Get first place id from trigger meta language
        return parser.get_places(0)[0].get('uuid')

    id: str
    lifetime: int = strawberry.field(resolver=resolve_lifetime)
    limit: int = strawberry.field(resolver=resolve_limit)
    location_id: str = strawberry.field(resolver=resolve_location)


@strawberry.type
class TriggerManageOutput(MutationResult):
    trigger: TriggerOutput = strawberry.field(description="Trigger object")


@strawberry.type
class TriggerNewManageOutput(MutationResult):
    trigger: TriggerNewOutput = strawberry.field(description="Trigger new object")


@strawberry.type(description="Representation of notification object")
class NotificationOutput:
    id: ID = strawberry.field(description="Notification id")
    is_active: bool = strawberry.field(description="Determines whether notification is active")
    is_viewed: bool = strawberry.field(description="Determines whether the notification has been viewed")

    @strawberry.field(description="Notification creation date")
    def creation_date(root) -> Optional[str]:
        if root.meta.get('type') == 'location_overflow':
            return (root.creation_date + timedelta(seconds=root.meta['lifetime'])).isoformat()
        else:
            return root.creation_date.isoformat()

    @strawberry.field(description="Title of location where camera is")
    def location_title(root) -> Optional[str]:
        return root.meta.get('location_title', '')

    @strawberry.field(description="Id of location where camera is")
    def location_id(root) -> Optional[str]:
        return root.meta.get('location_id', '')

    @strawberry.field(description="Type of notification")
    def type(root) -> Optional[str]:
        return root.meta.get('type')

    @strawberry.field(description="Id of the activity associated with the notification")
    def activity_id(root) -> Optional[str]:
        return root.meta.get('activity_id')

    @strawberry.field(description="Id of the person's main sample")
    def main_sample_id(root) -> Optional[str]:
        person = apps.get_model('person_domain', 'Person')
        person_id = root.meta.get('person_id')
        return person.objects.get(id=person_id).profile.info.get('main_sample_id') if person_id else None

    @strawberry.field(description="Person's description")
    def description(root) -> Optional[str]:
        person = apps.get_model('person_domain', 'Person')
        person_id = root.meta.get('person_id')
        return person.objects.get(id=person_id).profile.info.get('description') if person_id else None

    @strawberry.field(description="Id of the person's realtime face photo")
    def realtime_face_photo_id(root) -> Optional[str]:
        return root.meta.get('realtime_face_photo_id')

    @strawberry.field(description="Id of the person's realtime body photo")
    def realtime_body_photo_id(root) -> Optional[str]:
        return root.meta.get('realtime_body_photo_id')

    @strawberry.field(description="Id of the person for whom the notification was created")
    def person_id(root) -> Optional[str]:
        return root.meta.get('person_id')

    @strawberry.field(description="Id of profile_group associated with the person")
    def profile_group_id(root) -> Optional[str]:
        return root.meta.get('profile_group_id')

    @strawberry.field(description="Limiting the number of people in a location")
    def limit(root) -> Optional[int]:
        return root.meta.get('limit')

    @strawberry.field(description="Current number of people in the location")
    def current_count(root) -> Optional[int]:
        return root.meta.get('current_count')


@strawberry.type
class EndpointManageOutput(MutationResult):
    endpoint: TriggerOutput = strawberry.field(description="Endpoint object")


@strawberry.type
class EndpointCollection:
    total_count: int
    collection_items: List[EndpointOutput]


NotificationCollection = strawberry.type(get_collection(NotificationOutput, 'NotificationCollection'))
TriggerCollection = strawberry.type(get_collection(TriggerOutput, 'TriggerCollection'))
TriggerNewCollection = strawberry.type(get_collection(TriggerNewOutput, 'NewTriggerCollection'))

notification_map = {'locationId': 'meta__location_id', 'limit': 'meta__limit', 'lifetime': 'meta__lifetime',
                    'personId': 'meta__person_id', 'profileGroupId': 'meta__profile_group_id',
                    'type': 'meta__type', 'isActive': 'is_active', 'isViewed': 'is_viewed',
                    'lastModified': 'last_modified', 'creationDate': 'creation_date'}
trigger_map = {'locationId': 'meta__location_id', 'limit': 'meta__limit', 'lifetime': 'meta__lifetime'}
trigger_new_map = {'placeIds': 'meta__linked_places__contains', 'targetIds': 'meta__linked_targets__contains'}
