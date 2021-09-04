import os
from typing import List, Optional
from functools import reduce

import strawberry
from strawberry import ID
from strawberry.types import Info
from django.db.models import Q

from platform_lib.strawberry_auth.permissions import IsHaveAccess
from .types import ActivityCollection, SampleType, DjangoModelType, StrawberryModelType, OngoingsCollection
from data_domain.models import Activity, Sample
from platform_lib.types import Collection, JSONString
from platform_lib.utils import get_filters, get_slice, get_workspace_id
from user_domain.models import Workspace
from data_domain.managers import OngoingManager
from data_domain.api.v1.types import activity_map


def resolve_model(model: DjangoModelType, query_filter: Optional[Q] = None) -> List[StrawberryModelType]:
    if query_filter:
        return model.objects.filter(query_filter).all()
    return model.objects.all()


def resolve_activities(root, info: Info,
                       ids: Optional[List[str]] = None,
                       order: Optional[List[str]] = None,
                       filter: Optional[JSONString] = None,
                       limit: Optional[int] = None,
                       offset: Optional[int] = None) -> ActivityCollection:
    workspace_id = get_workspace_id(info)
    query_filter = Q(workspace=Workspace.objects.get(id=workspace_id))  # noqa

    if filter is not None:
        query_filter &= get_filters(filter)

    activities = resolve_model(Activity, query_filter)  # noqa

    if ids is not None:
        activities = activities.filter(id__in=ids)

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   activity_map.items(),
                   order_string) for order_string in order
        ]
        activities = activities.order_by(*order)

    total_count = activities.count()
    activities = get_slice(activities, offset=offset, limit=limit)

    return Collection(total_count=total_count, collection_items=activities)  # noqa


def resolve_ongoings(info: Info, location_id: Optional[ID] = ''):
    workspace_id = get_workspace_id(info)
    ongoings = OngoingManager.get_ongoings(workspace_id, location_id)

    return OngoingsCollection(total_count=len(ongoings), collection_items=ongoings)


def resolve_samples(root, info: Info) -> List[SampleType]:
    workspace_id = get_workspace_id(info)
    workspace_filter = Q(workspace=Workspace.objects.get(id=workspace_id))
    return resolve_model(Sample, workspace_filter)  # noqa


@strawberry.type
class Query:
    activities: ActivityCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                      resolver=resolve_activities)
    samples: List[SampleType] = strawberry.field(permission_classes=[IsHaveAccess],
                                                 resolver=resolve_samples)
    ongoings: OngoingsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                    resolver=resolve_ongoings)


schema = strawberry.Schema(query=Query)
