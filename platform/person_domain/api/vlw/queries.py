import os
import django
import strawberry

from platform_lib.utils import paginated_field_generator

from person_domain.api.v2.queries import Query as Query_v2
from person_domain.api.v2.queries import resolve_profiles_raw as resolve_profiles_raw_v2

from person_domain.api.vlw.types import ProfilesCollection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


def resolve_profiles_raw(*args, **kwargs) -> ProfilesCollection:
    collection = resolve_profiles_raw_v2(*args, **kwargs)
    return ProfilesCollection(collection.total_count, collection.collection_items)


resolve_profiles = paginated_field_generator(resolve_profiles_raw)


@strawberry.type
class Query(Query_v2):
    profiles: ProfilesCollection = strawberry.field(resolver=resolve_profiles, description="List of profiles")
