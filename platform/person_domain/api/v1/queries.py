import os
from typing import List, Optional
from functools import reduce

import django
from django.db.models import Q
import strawberry
from strawberry import ID
from strawberry.types import Info

from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.utils import get_filters, get_slice, get_workspace_id
from platform_lib.types import JSONString
from person_domain.models import Person, Profile
from person_domain.api.v1.types import PersonsCollection, ProfilesCollection, person_map, profile_map  # noqa

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


def resolve_profiles(root, info: Info,
                     ids: Optional[List[Optional[ID]]] = None,
                     order: Optional[List[str]] = None,
                     filter: Optional[JSONString] = None,
                     limit: Optional[int] = None,
                     offset: Optional[int] = None) -> ProfilesCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id)

    if ids:
        query &= Q(id__in=ids)
    if filter:
        query &= get_filters(filter)

    profiles = Profile.objects.filter(query)
    total_count = profiles.count()

    if order:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   profile_map.items(),
                   order_string) for order_string in order
        ]
        profiles = profiles.order_by(*order)

    profiles = get_slice(profiles, offset=offset, limit=limit)

    return ProfilesCollection(total_count=total_count, collection_items=profiles)


def resolve_persons(root, info: Info,
                    ids: Optional[List[Optional[ID]]] = None,
                    order: Optional[List[str]] = None,
                    filter: Optional[JSONString] = None,
                    limit: Optional[int] = None,
                    offset: Optional[int] = None) -> PersonsCollection:
    workspace_id = get_workspace_id(info)
    query = Q(workspace__id=workspace_id)

    if ids is not None:
        query &= Q(id__in=ids)
    if filter:
        diff = {}
        for old_key in filter.keys():
            diff[old_key] = reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                                   person_map.items(),
                                   old_key)
        for old_key, new_key in diff.items():
            filter[new_key] = filter.pop(old_key)
        query &= get_filters(filter)

    persons = Person.objects.filter(query)
    total_count = persons.count()

    if order:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   person_map.items(),
                   order_string) for order_string in order
        ]
        persons = persons.order_by(*order)

    persons = get_slice(persons, offset=offset, limit=limit)

    return PersonsCollection(total_count=total_count, collection_items=persons)


def resolve_candidates(root, info: Info, activity_id: Optional[str]):
    return []


@strawberry.type
class Query:
    persons: PersonsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                  resolver=resolve_persons)
    profiles: ProfilesCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                    resolver=resolve_profiles)
    candidates: Optional[List[JSONString]] = strawberry.field(permission_classes=[IsHaveAccess],
                                                              resolver=resolve_candidates)
