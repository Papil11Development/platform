import datetime
import uuid
from datetime import timedelta
from enum import Enum
from typing import Optional, List
from uuid import UUID

import strawberry
import strawberry_django
from django.apps import apps
from django.conf import settings
from django.db.models import Q, F, QuerySet
from strawberry import ID, auto
from strawberry.arguments import UNSET

from notification_domain.managers import EndpointManager
from notification_domain.models import Endpoint, Notification
from label_domain.managers import LabelManager
from collector_domain.managers import CameraManager
from platform_lib.managers import TriggerMetaManager
from platform_lib.types import MutationResult, JSONString, FilterLookupCustom
from platform_lib.utils import get_collection, from_dict_to_class, FilterByWorkspaceMixin, get_workspace_id


@strawberry.enum
class EndpointType(Enum):
    Email = 'EM'
    Webhook = 'WH'
    WebInterface = "WI"


@strawberry.enum
class NotificationType(Enum):
    LOCATION_OVERFLOW = 'location_overflow'
    PRESENCE = 'presence'


DefaultEndpointAlias = strawberry.enum(EndpointManager.DefaultAlias)


@strawberry.input(description="Information needed to create an email endpoint")
class EmailEndpointInput:
    target_email: str = strawberry.field(description="Email to which events will be sent", default=None)


@strawberry.input(description="Information needed to create an webhook endpoint")
class WebhookEndpointInput:
    url: str = strawberry.field(description="Url to which requests will be sent", default=None)
    request_method: str = strawberry.field(description="Request method", default=None)


@strawberry.type(description='The destination point to which'
                             'the notification will be sent. For example: email or webhook')
class EndpointOutput:
    description_name = "endpoints"

    id: strawberry.ID
    type: EndpointType = strawberry.field(description="Endpoint type")
    meta: JSONString = strawberry.field(description="Endpoint meta information that contains"
                                                    " data needed to reach this endpoint")

    last_modified: datetime.datetime = strawberry.field(description="Date of endpoint last modification")
    creation_date: datetime.datetime = strawberry.field(description="Date of endpoint creation")

    @strawberry.field
    def default_alias(root) -> Optional[DefaultEndpointAlias]:
        return root.meta.get('default_alias')

    @strawberry.field(description="The object is in the archive")
    def archived(root) -> bool:
        return not root.is_active


@strawberry.type(description="Notification sending status information")
class EndpointStatusOutput:
    endpoint: EndpointOutput = strawberry.field(description='Endpoint object')
    status: str = strawberry.field(description='Sending status')


@strawberry_django.filters.filter(Notification)
class NotificationFilter:

    id: FilterLookupCustom[ID] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by ids"
    )
    creation_date: FilterLookupCustom[datetime.datetime] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by creation date"
    )
    last_modified: FilterLookupCustom[datetime.datetime] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by date of last modification"
    )
    is_viewed: bool = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by viewing status"
    )
    is_active: bool = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by active status"
    )
    endpoint_id: Optional[UUID] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by endpoint they have been sent to"
    )
    is_sent: Optional[bool] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications based on being sent/not sent to an endpoint"
    )
    trigger_id: Optional[ID] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by the trigger id"
    )
    profile_id: Optional[ID] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by the profile id"
    )
    type: Optional[NotificationType] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by type"
    )
    profile_group_title: Optional[str] = strawberry_django.field(
        default=UNSET,
        description="Filtering notifications by the profile group title"
    )

    def filter_endpoint_id(self, queryset):
        if self.endpoint_id is None:
            return queryset
        else:
            return queryset.filter(meta__statuses__has_key=str(self.endpoint_id))

    def filter_is_sent(self, queryset):
        if self.is_sent is None:
            return queryset
        else:
            notif_filter = Q(meta__has_key="statuses")
            return queryset.filter(notif_filter if self.is_sent else ~notif_filter)

    def filter_trigger_id(self, queryset):
        if self.trigger_id is None:
            return queryset
        else:
            return queryset.filter(meta__trigger_id=str(self.trigger_id))

    def filter_profile_id(self, queryset):
        if self.profile_id is None:
            return queryset
        else:
            return queryset.filter(meta__profile_id=str(self.profile_id))

    def filter_type(self, queryset):
        if self.type is None:
            return queryset
        else:
            return queryset.filter(meta__type=self.type.value)

    def filter_profile_group_title(self, queryset):
        if self.profile_group_title is None:
            return queryset
        else:
            return queryset.filter(meta__profile_group_title=self.profile_group_title)


@strawberry_django.ordering.order(Notification)
class NotificationOrdering:
    id: auto
    creation_date: auto
    last_modified: auto


@strawberry_django.type(Notification, description="Information describing the event that triggered the notification")
class NotificationOutput(FilterByWorkspaceMixin):
    class_name = "notification"

    id: ID = strawberry.field(description="Notification ID")
    is_active: bool = strawberry.field(description="Determines whether notification is active")
    is_viewed: bool = strawberry.field(description="Determines whether the notification has been viewed")
    last_modified: datetime.datetime = strawberry.field(description="Notification last modified date")

    def optimize_queryset_by_custom_joins(self, queryset, info, **kwargs) -> QuerySet:
        profile_model = apps.get_model('person_domain', 'Profile')
        profile_ids = map(uuid.UUID, queryset.values_list('meta__profile_id', flat=True))
        profiles = profile_model.objects.filter(id__in=profile_ids)

        for notif in queryset:
            notif.profile = next(
                filter(lambda profile: notif.meta.get('profile_id') == str(profile.id), profiles), None
            )

        return queryset

    def get_queryset(self, queryset, info, **kwargs) -> QuerySet:
        queryset = FilterByWorkspaceMixin.get_queryset(self, queryset, info, **kwargs)

        time_inaccuracy = 0.2

        notification_filter = ~Q(meta__type='location_overflow',
                                 last_modified__lt=F('creation_date') + timedelta(seconds=time_inaccuracy))

        queryset = queryset.filter(notification_filter)

        return queryset

    @strawberry.field(description="Notification creation date")
    def creation_date(root) -> datetime.datetime:
        if root.meta.get('type') == 'location_overflow':
            return root.creation_date + timedelta(seconds=root.meta['lifetime'])  # noqa
        else:
            return root.creation_date  # noqa

    @strawberry.field(description="Title of camera")
    def camera_title(root) -> Optional[str]:
        return CameraManager.get_camera_title(root.meta.get('camera_id'))

    @strawberry.field(description="Notification sending status to different endpoints")
    def endpoint_statuses(root) -> Optional[List[EndpointStatusOutput]]:
        return [EndpointStatusOutput(endpoint=Endpoint.objects.all(Q(id=key, is_active__in=[True, False])).first(),
                                     status=value)
                for key, value in root.meta.get("statuses", {}).items()]

    @strawberry.field(description="ID of camera")
    def camera_id(root) -> Optional[ID]:
        return root.meta.get('camera_id')

    @strawberry.field(description="Type of notification")
    def type(root) -> str:
        return root.meta.get('type')

    @strawberry.field(description="ID of the trigger which notification belongs to")
    def trigger_id(root) -> Optional[ID]:
        return root.meta.get('trigger_id')

    @strawberry.field(description="ID of the activity associated with the notification")
    def activity_id(root) -> Optional[ID]:
        return root.meta.get('activity_id')

    # TODO: Add return profile object instead of special fields (avatar_id, name, description and etc)
    @strawberry.field(description="ID of the profile's avatar")
    def avatar_id(root) -> Optional[ID]:
        if root.profile:
            return root.profile.info.get('avatar_id')
        return None

    @strawberry.field(description="Profile's name")
    def name(root) -> Optional[str]:
        if root.profile:
            return root.profile.info.get('name')
        return None

    @strawberry.field(description="Profile's description")
    def description(root) -> Optional[str]:
        if root.profile:
            return root.profile.info.get('description')
        return None

    @strawberry.field(description="ID of the profile's realtime face photo")
    def realtime_face_photo_id(root) -> Optional[str]:
        return root.meta.get('realtime_face_photo_id')

    @strawberry.field(description="ID of the profile's realtime body photo")
    def realtime_body_photo_id(root) -> Optional[str]:
        return root.meta.get('realtime_body_photo_id')

    @strawberry.field(description="ID of the profile for whom the notification was created")
    def profile_id(root) -> Optional[ID]:
        return root.meta.get('profile_id')

    @strawberry.field(description="ID of Profile Group associated with the profile")
    def profile_group_id(root) -> Optional[ID]:
        return root.meta.get('profile_group_id')

    @strawberry.field(description="Title of Profile Group associated with the profile")
    def profile_group_title(root) -> Optional[str]:
        profile_group_id = root.meta.get('profile_group_id')
        profile_group_title, _ = LabelManager.get_label_data(profile_group_id)
        return profile_group_title

    @strawberry.field(description="Color of Profile Group associated with the profile at the time of "
                                  "notification creation")
    def profile_group_color(root) -> Optional[str]:
        profile_group_id = root.meta.get('profile_group_id')
        _, profile_group_info = LabelManager.get_label_data(profile_group_id)
        return profile_group_info.get('color')

    @strawberry.field(description="Limiting the number of people in a location")
    def limit(root) -> Optional[int]:
        return root.meta.get('limit')

    @strawberry.field(description="Current number of people in the location")
    def current_count(root) -> Optional[int]:
        return root.meta.get('current_count')


@strawberry.type(description="Information about updated endpoint")
class EndpointManageOutput(MutationResult):
    endpoint: EndpointOutput = strawberry.field(description="Endpoint object")


@strawberry.type(description='A mechanism that is responsible for creating notifications. By analyzing the information'
                             'from the cameras, it determines whether a notification needs to be created.'
                             'The trigger is also responsible for sending notifications to the endpoints'
                             'that are associated with it.')
class TriggerType:
    description_name = "triggers"

    @strawberry.type
    class Meta:
        @strawberry.type
        class ConditionalLanguage:
            @strawberry.type
            class Variable:
                @strawberry.type
                class Target:
                    uuid: ID
                    type: str

                @strawberry.field
                def name(root) -> str:
                    return root['name']

                @strawberry.field
                def type(root) -> str:
                    return root['type']

                @strawberry.field
                def target(root) -> List[Target]:
                    return [from_dict_to_class(target) for target in root.get('target')]  # noqa

            @strawberry.field
            def variables(root) -> Optional[List[Variable]]:
                return [{'name': name, **variable} for name, variable in (root.get('variables') or {}).items()]  # noqa

            @strawberry.field
            def condition(root) -> Optional[str]:
                return root.get('condition')

        @strawberry.field
        def notification_params(root) -> Optional[JSONString]:
            return TriggerMetaManager(root).get_notification_params()  # noqa

        @strawberry.field
        def condition_language(root) -> Optional[ConditionalLanguage]:
            return TriggerMetaManager(root).get_condition_language()  # noqa

    id: ID

    creation_date: datetime.datetime
    last_modified: datetime.datetime

    @strawberry.field
    def title(root) -> str:
        return root.title

    @strawberry.field
    def meta(root) -> Meta:
        return root.meta  # noqa

    @strawberry.field
    def endpoints(root, offset: int = 0, limit: int = settings.QUERY_LIMIT) -> List[EndpointOutput]:
        limit = min(limit, settings.QUERY_LIMIT)
        return root.endpoints.all()[offset:offset+limit] # noqa

    @strawberry.field(description="The object is in the archive")
    def archived(root) -> bool:
        return not root.is_active


@strawberry.type(description="Information about updated or created trigger")
class TriggerManageOutput(MutationResult):
    trigger: TriggerType = strawberry.field(description="Trigger object")


EndpointCollection = strawberry.type(get_collection(EndpointOutput, 'EndpointCollection'))

TriggerCollection = strawberry.type(get_collection(TriggerType, 'TriggerCollection'))

trigger_map = {'endpointType': 'endpoints__type'}
