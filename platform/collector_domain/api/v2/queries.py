import strawberry

from django.conf import settings
from collector_domain.api.v2.types import AgentsCollection, agents_map
from collector_domain.models import Agent
from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.utils import paginated_field_generator, get_paginated_model, get_workspace_id


def resolve_agents_raw(*args, **kwargs):
    info = kwargs.get('info')
    ids = kwargs.get('ids')
    order = kwargs.get('order')
    offset = kwargs.get('offset')
    limit = kwargs.get('limit')
    model_filter = kwargs.get('filter')
    with_archived = kwargs.get('with_archived')
    with_archived_value = with_archived.value if with_archived is not None else None

    workspace_id = get_workspace_id(info)
    total_count, agents = get_paginated_model(model_class=Agent,
                                              workspace_id=workspace_id,
                                              ids=ids,
                                              order=order,
                                              offset=offset,
                                              limit=limit,
                                              model_filter=model_filter,
                                              filter_map=agents_map,
                                              with_archived=with_archived_value)

    return AgentsCollection(total_count=total_count, collection_items=agents)


resolve_agents = paginated_field_generator(resolve_agents_raw, with_archived=True)


@strawberry.type
class Query:
    agents: AgentsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                resolver=resolve_agents,
                                                description="Get a list of agents")
