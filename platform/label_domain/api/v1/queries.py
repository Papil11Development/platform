import os
from functools import reduce
from typing import List, Optional

import django
from django.db.models import Q
import strawberry
from strawberry import ID
from strawberry.types import Info

from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.types import JSONString
from platform_lib.utils import get_filters, get_slice, get_workspace_id
from label_domain.api.v1.types import ProfileGroupsCollection, LocationsCollection, AreaTypesCollection, \
    label_map

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from label_domain.models import Label  # noqa


def resolve_profile_groups(root, info: Info,
                           ids: Optional[List[Optional[ID]]] = None,
                           order: Optional[List[Optional[str]]] = None,
                           filter: Optional[JSONString] = None,
                           limit: Optional[int] = None,
                           offset: Optional[int] = None) -> ProfileGroupsCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id, type=Label.PROFILE_GROUP)

    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter, label_map)

    profile_groups = Label.objects.filter(query)

    total_count = profile_groups.count()

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   label_map.items(),
                   order_string) for order_string in order
        ]
        profile_groups = profile_groups.order_by(*order)

    profile_groups = get_slice(profile_groups, offset=offset, limit=limit)

    return ProfileGroupsCollection(total_count=total_count, collection_items=profile_groups)


def resolve_locations(root, info: Info,
                      ids: Optional[List[Optional[ID]]] = None,
                      order: Optional[List[Optional[str]]] = None,
                      filter: Optional[JSONString] = None,
                      limit: Optional[int] = None,
                      offset: Optional[int] = None) -> LocationsCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id, type=Label.LOCATION)

    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter, label_map)

    locations = Label.objects.filter(query)

    total_count = locations.count()

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   label_map.items(),
                   order_string) for order_string in order
        ]
        locations = locations.order_by(*order)

    locations = get_slice(locations, offset=offset, limit=limit)

    return LocationsCollection(total_count=total_count, collection_items=locations)


def resolve_area_types(root, info: Info,
                       ids: Optional[List[Optional[ID]]] = None,
                       order: Optional[List[Optional[str]]] = None,
                       filter: Optional[JSONString] = None,
                       limit: Optional[int] = None,
                       offset: Optional[int] = None) -> AreaTypesCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id, type=Label.AREA_TYPE)

    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter, label_map)

    area_types = Label.objects.filter(query)

    total_count = area_types.count()

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   label_map.items(),
                   order_string) for order_string in order
        ]
        area_types = area_types.order_by(*order)

    area_types = get_slice(area_types, offset=offset, limit=limit)

    return AreaTypesCollection(total_count=total_count, collection_items=area_types)


@strawberry.type
class Query:
    profile_groups: ProfileGroupsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                               resolver=resolve_profile_groups)
    locations: LocationsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                      resolver=resolve_locations)
    area_types: AreaTypesCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                       resolver=resolve_area_types)
