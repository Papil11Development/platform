import os

import django
import strawberry
from django.conf import settings

from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.utils import get_workspace_id, paginated_field_generator, get_paginated_model
from label_domain.api.v2.types import ProfileGroupsCollection, label_map

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from label_domain.models import Label  # noqa


def resolve_profile_groups_raw(*args, **kwargs) -> ProfileGroupsCollection:
    info = kwargs.get('info')
    ids = kwargs.get('ids')
    order = kwargs.get('order')
    offset = kwargs.get('offset')
    limit = kwargs.get('limit')
    model_filter = kwargs.get('filter')
    with_archived = kwargs.get('with_archived')
    with_archived_value = getattr(with_archived, "value", None)

    workspace_id = get_workspace_id(info)
    total_count, profile_groups = get_paginated_model(model_class=Label,
                                                      workspace_id=workspace_id,
                                                      ids=ids,
                                                      order=order,
                                                      offset=offset,
                                                      limit=limit,
                                                      model_filter=model_filter,
                                                      filter_map=label_map,
                                                      with_archived=with_archived_value)

    return ProfileGroupsCollection(total_count=total_count, collection_items=profile_groups)


resolve_profile_groups = paginated_field_generator(resolve_profile_groups_raw, with_archived=True)


@strawberry.type
class Query:
    profile_groups: ProfileGroupsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                               resolver=resolve_profile_groups,
                                                               description="List of profile groups")
