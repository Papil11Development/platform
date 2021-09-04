from datetime import timedelta
import os
from functools import reduce
from typing import List, Optional

import django
from django.db.models import Q, F
import strawberry
from strawberry.types import Info

from platform_lib.managers import TriggerMetaManager
from platform_lib.meta_language_parser import MetaLanguageParser
from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.types import JSONString
from platform_lib.utils import get_filters, get_slice, get_workspace_id

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from notification_domain.models import Endpoint, Trigger, Notification  # noqa
from notification_domain.api.v1.types import TriggerCollection, EndpointCollection, TriggerNewCollection, \
    trigger_new_map, trigger_map, notification_map, NotificationCollection  # noqa


def resolve_endpoints(root, info: Info,
                      ids: Optional[List[str]] = None,
                      filter: Optional[JSONString] = None,
                      limit: Optional[int] = None,
                      offset: Optional[int] = None) -> EndpointCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id)
    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter)

    endpoints = Endpoint.objects.filter(query)

    total_count = endpoints.count()

    endpoints = get_slice(endpoints, limit=limit, offset=offset)

    return EndpointCollection(total_count=total_count, collection_items=endpoints)


def resolve_triggers(root, info: Info,
                     ids: Optional[List[str]] = None,
                     filter: Optional[JSONString] = None,
                     limit: Optional[int] = None,
                     offset: Optional[int] = None) -> TriggerCollection:
    workspace_id = get_workspace_id(info)

    # get place id from filter and delete it for not affecting updated triggers filtration
    place_id = filter.pop('meta__location_id', None)

    workspace_triggers = Trigger.objects.filter(workspace_id=workspace_id).values_list('id', 'meta')

    place_trigger_ids = {
        str(trigger[0])
        for trigger in workspace_triggers
        if MetaLanguageParser(TriggerMetaManager(trigger[1]).get_condition_language()).is_have_place(place_id)
    }

    query = Q(workspace__id=workspace_id)
    if ids:
        query &= Q(id__in=(set(ids) & place_trigger_ids))
    else:
        query &= Q(id__in=place_trigger_ids)
    if filter:
        query &= get_filters(filter, trigger_map)

    triggers = Trigger.objects.filter(query)

    total_count = triggers.count()

    triggers = get_slice(triggers, limit=limit, offset=offset)

    return TriggerCollection(total_count=total_count, collection_items=triggers)


def resolve_new_triggers(root, info: Info,
                         ids: Optional[List[str]] = None,
                         filter: Optional[JSONString] = None,
                         limit: Optional[int] = None,
                         offset: Optional[int] = None) -> TriggerNewCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id)
    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter, trigger_new_map)

    triggers = Trigger.objects.filter(query)

    total_count = triggers.count()

    triggers = get_slice(triggers, limit=limit, offset=offset)

    return TriggerNewCollection(total_count=total_count, collection_items=triggers)


def resolve_notification(root, info: Info,
                         ids: Optional[List[str]] = None,
                         order: Optional[List[str]] = None,
                         filter: Optional[JSONString] = None,
                         limit: Optional[int] = None,
                         offset: Optional[int] = None) -> NotificationCollection:
    time_inaccuracy = 0.2
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id)
    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter, notification_map)

    notifications = Notification.objects.filter(query).exclude(meta__type='location_overflow',
                                                               last_modified__lt=F('creation_date') + timedelta(
                                                                   seconds=time_inaccuracy))

    total_count = notifications.count()

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   notification_map.items(),
                   order_string) for order_string in order
        ]
        notifications = notifications.order_by(*order)

    notifications = get_slice(notifications, limit=limit, offset=offset)

    return NotificationCollection(total_count=total_count, collection_items=notifications)


@strawberry.type
class Query:
    endpoints: EndpointCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                     resolver=resolve_endpoints)
    triggers: TriggerCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                   resolver=resolve_triggers)
    new_triggers: TriggerNewCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                          resolver=resolve_new_triggers)
    notifications: JSONString = strawberry.field(permission_classes=[IsHaveAccess],
                                                 resolver=resolve_notification)
