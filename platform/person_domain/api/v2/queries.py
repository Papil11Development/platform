import os
import django
import strawberry
from strawberry.types import Info
from django.conf import settings
from django.db.models import IntegerField, DateField, Func
from django.db.models.functions import Coalesce, Cast
from django.contrib.postgres.fields.jsonb import KeyTextTransform

from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.utils import get_workspace_id, paginated_field_generator, get_paginated_model
from person_domain.models import Profile, ProfileSettings
from person_domain.api.v2.types import ProfilesCollection, profile_map, ProfileSettingsType
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
    profile_selections = next(filter(lambda x: x.name == 'profiles', info.selected_fields))
    try:
        next(filter(lambda x: x.name == 'totalCount', profile_selections.selections))
        get_total_count = True
    except StopIteration:
        get_total_count = False
    workspace_id = get_workspace_id(info)

    predefine_queryset = Profile.objects.annotate(
        age=Coalesce(
            Func(
                Func(
                    Cast(KeyTextTransform('birthday', 'info'), output_field=DateField()),
                    function='AGE'),
                function='DATE_PART', template="%(function)s('year', %(expressions)s)",
                output_field=IntegerField()
            ),
            Cast(
                KeyTextTransform('age', 'info'),
                output_field=IntegerField()
            )
        )
    )

    total_count, profiles = get_paginated_model(model_class=Profile,
                                                workspace_id=workspace_id,
                                                ids=ids,
                                                order=order,
                                                offset=offset,
                                                limit=limit,
                                                model_filter=model_filter,
                                                filter_map=profile_map,
                                                predefine_queryset=predefine_queryset,
                                                optimize_query=optimizer_profile_queryset,
                                                get_total_count=get_total_count)

    return ProfilesCollection(total_count=total_count, collection_items=profiles)


resolve_profiles = paginated_field_generator(resolve_profiles_raw)


@strawberry.type
class Query:
    profiles: ProfilesCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                    resolver=resolve_profiles,
                                                    description="List of profiles")

    @strawberry.field(permission_classes=[IsHaveAccess])
    def profileSettings(self, info: Info) -> ProfileSettingsType:
        workspace_id = get_workspace_id(info)
        p_settings, created = ProfileSettings.objects.get_or_create(workspace_id=workspace_id)
        if created:
            p_settings.extra_fields = settings.REQUIRED_PROFILE_FIELDS
            p_settings.save()
        return p_settings
