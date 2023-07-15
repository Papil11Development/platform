from typing import List, Optional

import strawberry
from strawberry import ID
from strawberry.types import Info

from data_domain.api.v2.queries import Query as Query_v2
from data_domain.api.vlw.types import SearchTypeLuna, SampleCollection, sample_map
from data_domain.models import Sample

from platform_lib.types import JSON, CustomBinaryType
from platform_lib.utils import paginated_field_generator, get_workspace_id, get_paginated_model


def resolve_samples_raw(*args, **kwargs) -> SampleCollection:
    info = kwargs.get('info')
    ids = kwargs.get('ids')
    order = kwargs.get('order')
    offset = kwargs.get('offset')
    limit = kwargs.get('limit')
    model_filter = kwargs.get('filter')

    workspace_id = get_workspace_id(info)
    total_count, samples = get_paginated_model(model_class=Sample,
                                               workspace_id=workspace_id,
                                               ids=ids,
                                               order=order,
                                               offset=offset,
                                               limit=limit,
                                               model_filter=model_filter,
                                               filter_map=sample_map)

    return SampleCollection(total_count=total_count, collection_items=samples)  # noqa


resolve_samples = paginated_field_generator(resolve_samples_raw)


@strawberry.type
class Query(Query_v2):
    samples: SampleCollection = strawberry.field(resolver=resolve_samples, description="Get a list of samples")

    @strawberry.field(description="Search similar people in a workspace based on images, sample data, or sample IDs")
    def search(self, info: Info,
               source_sample_ids: Optional[List[ID]] = None,
               source_sample_data: Optional[JSON] = None,
               source_image: Optional[CustomBinaryType] = None,
               scope: Optional[ID] = None,
               confidence_threshold: Optional[float] = 0.0,
               max_num_of_candidates_returned: Optional[int] = 5) -> List[SearchTypeLuna]:

        return Query_v2.search(**locals())  # noqa
