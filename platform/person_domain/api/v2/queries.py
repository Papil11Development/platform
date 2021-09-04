import os
import django
import strawberry
from django.conf import settings

from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.utils import get_workspace_id, paginated_field_generator, get_paginated_model
from person_domain.models import Profile
from person_domain.api.v2.types import ProfilesCollection, profile_map
from person_domain.api.utils import optimizer_profile_queryset

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


def resolve_profiles_raw(*args, **kwargs) -> ProfilesCollection:
    info = kwargs.get('info')
    ids = kwargs.get('ids')
    order = kwargs.get('order')
    offset = kwargs.get('offset')
    limit = kwargs.get('limit')
    model_filter = kwargs.get('filter')

    workspace_id = get_workspace_id(info)

    total_count, profiles = get_paginated_model(model_class=Profile,
                                                workspace_id=workspace_id,
                                                ids=ids,
                                                order=order,
                                                offset=offset,
                                                limit=limit,
                                                model_filter=model_filter,
                                                filter_map=profile_map,
                                                optimize_query=optimizer_profile_queryset)

    return ProfilesCollection(total_count=total_count, collection_items=profiles)


resolve_profiles = paginated_field_generator(resolve_profiles_raw)


@strawberry.type
class Query:
    profiles: ProfilesCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                    resolver=resolve_profiles,
                                                    description="List of profiles")
