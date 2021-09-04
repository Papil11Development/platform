import os
from typing import Optional

import django
import strawberry
from django.conf import settings
from strawberry import ID

from notification_domain.api.v2.types import trigger_map, TriggerCollection, NotificationOutput, \
    NotificationOrdering, NotificationFilter
from platform_lib.managers import TriggerMetaManager
from platform_lib.meta_language_parser import MetaLanguageParser
from platform_lib.types import CountList
from platform_lib.utils import get_workspace_id, get_paginated_model, paginated_field_generator, \
    StrawberryDjangoCountList
from platform_lib.strawberry_auth.permissions import IsHaveAccess

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from notification_domain.models import Endpoint, Trigger  # noqa
from notification_domain.api.v2.types import EndpointCollection  # noqa


def resolve_endpoint_raw(*args, **kwargs) -> EndpointCollection:
    info = kwargs.get('info')
    ids = kwargs.get('ids')
    order = kwargs.get('order')
    offset = kwargs.get('offset')
    limit = kwargs.get('limit')
    model_filter = kwargs.get('filter')
    with_archived = kwargs.get('with_archived')
    with_archived_value = with_archived.value if with_archived is not None else None

    workspace_id = get_workspace_id(info)
    total_count, endpoints = get_paginated_model(model_class=Endpoint,
                                                 workspace_id=workspace_id,
                                                 ids=ids,
                                                 order=order,
                                                 offset=offset,
                                                 limit=limit,
                                                 model_filter=model_filter,
                                                 with_archived=with_archived_value)

    return EndpointCollection(total_count=total_count, collection_items=endpoints)


def resolve_triggers_raw(*args, **kwargs):
    info = kwargs.get('info')
    ids = kwargs.get('ids')
    order = kwargs.get('order')
    offset = kwargs.get('offset')
    limit = kwargs.get('limit')
    model_filter = kwargs.get('filter')
    target_id = kwargs.get('target_id')
    with_archived = kwargs.get('with_archived')
    with_archived_value = with_archived.value if with_archived is not None else None

    workspace_id = get_workspace_id(info)

    if target_id is not None:
        workspace_triggers = Trigger.objects.filter(workspace_id=workspace_id).values_list('id', 'meta')

        target_trigger_ids = {
            str(trigger[0])
            for trigger in workspace_triggers
            if MetaLanguageParser(TriggerMetaManager(trigger[1]).get_condition_language()).is_have_target(target_id)
        }

        if ids:
            ids = set(ids) & target_trigger_ids
        else:
            ids = target_trigger_ids

    total_count, triggers = get_paginated_model(model_class=Trigger,
                                                workspace_id=workspace_id,
                                                ids=ids,
                                                order=order,
                                                offset=offset,
                                                limit=limit,
                                                model_filter=model_filter,
                                                filter_map=trigger_map,
                                                with_archived=with_archived_value)

    return TriggerCollection(total_count=total_count, collection_items=triggers)


resolve_triggers = paginated_field_generator(resolve_triggers_raw, extra_args={"target_id": Optional[ID]},
                                             with_archived=True)
resolve_endpoint = paginated_field_generator(resolve_endpoint_raw, with_archived=True)


@strawberry.type
class Query:
    endpoints: EndpointCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                     resolver=resolve_endpoint,
                                                     description="List of endpoints")

    notifications: CountList[NotificationOutput] = StrawberryDjangoCountList(permission_classes=[IsHaveAccess],
                                                                             description="List of notifications",
                                                                             filters=NotificationFilter,
                                                                             order=NotificationOrdering,
                                                                             pagination=True)

    triggers: TriggerCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                   resolver=resolve_triggers,
                                                   description="List of triggers")
