from functools import reduce

from django.db.models import Q
from collector_domain.api.v1.types import device_map, camera_map, roi_map
from collector_domain.models import Agent, Camera, AttentionArea
from platform_lib.utils import get_filters


def get_agents(token: str, filter: dict = None, order: list = None, ids: list = None, with_archived: str = None):
    query_filter = Q(workspace__accesses__id=token)

    if ids is not None:
        query_filter &= Q(id__in=ids)

    if filter is not None:
        query_filter &= get_filters(filter, device_map)

    if with_archived is None:
        queryset = Agent.objects.filter(query_filter).distinct()
    elif with_archived.lower() == 'all':
        query_filter &= Q(is_active__in=[True, False])
        queryset = Agent.objects.all(query_filter).distinct()
    elif with_archived.lower() == 'archived':
        query_filter &= Q(is_active=False)
        queryset = Agent.objects.all(query_filter).distinct()
    else:
        queryset = Agent.objects.filter(query_filter).distinct()
    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   device_map.items(),
                   order_string) for order_string in order
        ]
        queryset = queryset.order_by(*order)
    return queryset


def get_cameras(token: str, filter: dict = None, order: list = None, ids: list = None, with_archived: str = None):
    query_filter = Q(workspace__accesses__id=token)

    if ids is not None:
        query_filter &= Q(id__in=ids)

    if filter is not None:
        query_filter &= get_filters(filter, camera_map)

    if with_archived is None:
        queryset = Camera.objects.filter(query_filter).distinct()
    elif with_archived.lower() == 'all':
        query_filter &= Q(is_active__in=[True, False])
        queryset = Camera.objects.all(query_filter).distinct()
    elif with_archived.lower() == 'archived':
        query_filter &= Q(is_active=False)
        queryset = Camera.objects.all(query_filter).distinct()
    else:
        queryset = Camera.objects.filter(query_filter).distinct()
    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   camera_map.items(),
                   order_string) for order_string in order
        ]
        queryset = queryset.order_by(*order)
    return queryset


def get_attention_areas(token: str,
                        filter: dict = None,
                        order: list = None,
                        ids: list = None,
                        with_archived: str = None):

    query_filter = Q(workspace__accesses__id=token)

    if filter is not None:
        query_filter &= get_filters(filter, roi_map)

    queryset = AttentionArea.objects.filter(query_filter).distinct()

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   roi_map.items(),
                   order_string) for order_string in order
        ]
        queryset = queryset.order_by(*order)
    return queryset
