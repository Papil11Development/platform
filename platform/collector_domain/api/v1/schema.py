import strawberry
from strawberry.tools import merge_types

from collector_domain.api.v1 import mutations
from collector_domain.api.utils import get_agents, get_cameras, get_attention_areas
from collector_domain.api.v1.types import AgentsCollection, CamerasCollection, AttentionAreasCollection
from platform_lib.strawberry_auth.permissions import IsHaveAccess
from platform_lib.utils import get_slice, paginated_field_generator, get_token


@strawberry.type
class Query:

    def resolve_attention_areas_raw(*args, **kwargs):
        attention_areas = get_attention_areas(get_token(kwargs.get('info')),
                                              kwargs.get('filter'),
                                              kwargs.get('order', ['id']),
                                              ids=kwargs.get('ids'))
        total_count = attention_areas.count()
        attention_areas = get_slice(attention_areas, offset=kwargs.get('offset'), limit=kwargs.get('limit'))
        return AttentionAreasCollection(total_count=total_count, collection_items=attention_areas)

    def resolve_cameras_raw(*args, **kwargs):
        with_archived = kwargs.get('with_archived')
        with_archived_value = with_archived.value if with_archived is not None else None

        cameras = get_cameras(get_token(kwargs.get('info')), kwargs.get('filter'), kwargs.get('order', ['id']),
                              ids=kwargs.get('ids'), with_archived=with_archived_value)
        total_count = cameras.count()

        cameras = get_slice(cameras, offset=kwargs.get('offset'), limit=kwargs.get('limit'))

        return CamerasCollection(total_count=total_count, collection_items=cameras)

    def resolve_agents_raw(*args, **kwargs):
        with_archived = kwargs.get('with_archived')
        with_archived_value = with_archived.value if with_archived is not None else None

        agents = get_agents(get_token(kwargs.get('info')), kwargs.get('filter'), kwargs.get('order', ['id']),
                            ids=kwargs.get('ids'), with_archived=with_archived_value)
        total_count = agents.count()

        agents = get_slice(agents, offset=kwargs.get('offset'), limit=kwargs.get('limit'))
        return AgentsCollection(total_count=total_count, collection_items=agents)

    resolve_attention_areas = paginated_field_generator(resolve_attention_areas_raw)
    resolve_cameras = paginated_field_generator(resolve_cameras_raw, with_archived=True)
    resolve_agents = paginated_field_generator(resolve_agents_raw, with_archived=True)

    rois: AttentionAreasCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                      resolver=resolve_attention_areas)
    cameras: CamerasCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                  resolver=resolve_cameras)
    agents: AgentsCollection = strawberry.field(permission_classes=[IsHaveAccess],
                                                resolver=resolve_agents)


Mutation = merge_types("Mutation", (mutations.LocationLinkMutation, mutations.AgentMutation))

schema = strawberry.Schema(query=Query, mutation=Mutation)
