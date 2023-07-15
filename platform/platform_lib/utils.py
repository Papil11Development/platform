import json
import uuid
import base64
import re
import os
import threading
from collections import ChainMap
from inspect import Signature, Parameter

from enum import Enum
from pathlib import Path

import django
import strawberry
import pytz
import requests
from django.urls import reverse
from django.utils.html import format_html, escape
from plib.tracing.utils import get_current_tracing_context
from requests.exceptions import ConnectionError, HTTPError
from PIL import ImageOps
from abc import ABC, abstractmethod
from channels.layers import get_channel_layer
from dateutil import parser as date_parser
from datetime import datetime, timezone
from functools import reduce, wraps
# TODO: add Annotated type after python>=3.9
from typing import List, Optional, Tuple, Union, Dict, Any, Callable
from strawberry import ID
from strawberry.arguments import UNSET
from strawberry.types import Info
from graphql import GraphQLError
from django.db import models
from django.db.models import Q, QuerySet, signals
from django.db.transaction import atomic
from asgiref.sync import SyncToAsync, async_to_sync

from io import BytesIO
from urllib.parse import urlparse
from PIL.Image import open as open_image, Image
from PIL import UnidentifiedImageError
from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from platform_lib.exceptions import BadInputDataException
from platform_lib.types import emotions_map, keypoints_map, JSONString, WithArchived, EyesInput, PointInputType, \
    CountList, FilterLookupCustom
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import usage_analytics_schema
from strawberry_django import utils
from strawberry_django.fields.field import StrawberryDjangoField
from strawberry_django.pagination import apply as apply_pagination
from strawberry_django.filters import apply as apply_filters
from strawberry_django.ordering import apply as apply_ordering
from django.db.models import QuerySet


class OffsetPaginationInput:
    limit: int = settings.QUERY_LIMIT
    offset: int = 0


class SampleObjectsName(str, Enum):
    PROCESSING_CAPTURER = Path(settings.PROCESSING_SERVICE_CAPTURER).stem


def _get_type_from_count(type: Any):
    items_type = [f.type for f in type._type_definition._fields if f.name == 'collection_items']

    return utils.unwrap_type(items_type[0]) if items_type else None


class FilterByWorkspaceMixin:
    def get_queryset(self, queryset, info, **kwargs):
        workspace_id = get_workspace_id(info)
        return queryset.filter(workspace_id=workspace_id)


class StrawberryDjangoCountList(StrawberryDjangoField):
    @property
    def is_list(self):
        return True

    @property
    def django_model(self):
        # Get model type from collection_items field of CountList type
        if type_ := _get_type_from_count(self.type):
            return utils.get_django_model(type_)
        else:
            return None

    def get_queryset(self, queryset: QuerySet[Any], info, pagination=OffsetPaginationInput, filters=UNSET, order=UNSET,
                     **kwargs):
        def none_to_unset(filter_):
            for key_, value_ in vars(filter_).items():
                if value_ is None:
                    setattr(filter_, key_, UNSET)

        # prepare filters to replace none values to UNSET
        for value in vars(filters).values():
            if isinstance(value, FilterLookupCustom):
                none_to_unset(value)

        queryset = apply_filters(filters, queryset)
        queryset = apply_ordering(order, queryset)

        optimize_queryset_by_custom_joins = None
        get_queryset = None
        if type_ := _get_type_from_count(self.type):
            get_queryset = getattr(type_, 'get_queryset', None)
            optimize_queryset_by_custom_joins = getattr(type_, 'optimize_queryset_by_custom_joins', None)

        # use additional filters from type's get_queryset method.
        # MUST BE AFTER other filters and ordering because of query optimization
        if get_queryset:
            queryset = get_queryset(self, queryset, info, **kwargs)

        self.total_count = queryset.count()  # noqa calculate and apply total_count to result for futher representation
        pagination.limit = min(pagination.limit, settings.QUERY_LIMIT)
        queryset = apply_pagination(pagination, queryset)

        # MUST BE AFTER pagination for proper limiting requested entities
        if optimize_queryset_by_custom_joins:
            queryset = optimize_queryset_by_custom_joins(self, queryset, info, **kwargs)

        return queryset

    def resolver(self, info, source, **kwargs):
        qs = super().resolver(info, source, **kwargs)
        return CountList[self.type](
            total_count=self.total_count,  # noqa get total_count from get_queryset
            collection_items=qs,
        )


def from_dict_to_class(attrs: Dict, class_name: Optional[str] = 'ClassDict') -> object:
    return type(class_name, (), attrs)


def isoformat_time(time: Union[str, int], time_format: Optional[str] = None) -> str:
    """
    Convert time string or timestamp int to isoformat string use format to convert form string if presented
    Parameters
    ----------
    time: Union[str, int]
        time in string or int timestamp format
    time_format: Optional[str]
        time format if presented
    Returns
    -------
    str:
        time in isoformat string
    """
    if type(time) is int:
        return datetime.fromtimestamp(time / 1000.0, tz=timezone.utc).isoformat()
    if type(time) is str:
        if time_format is not None:
            return datetime.strptime(time, time_format).isoformat()
        else:
            return datetime.fromisoformat(time).isoformat()


def get_paginated_model(model_class,
                        workspace_id: Union[str, uuid.UUID],
                        ids: Union[list, set] = None,
                        order: list = None,
                        offset: int = 0,
                        limit: int = settings.QUERY_LIMIT,
                        model_filter: dict = None,
                        filter_map: dict = None,
                        model_exclude: dict = None,
                        with_archived: str = None,
                        predefine_queryset: QuerySet = None,
                        optimize_query: Callable = None,
                        get_total_count: bool = True) -> Tuple[int, QuerySet]:
    query_filter = Q(workspace__id=workspace_id)

    if ids is not None:
        query_filter &= Q(id__in=ids)
    if model_exclude:
        query_filter &= ~get_filters(model_exclude, filter_map)
    if model_filter:
        query_filter &= get_filters(model_filter, filter_map)

    if predefine_queryset is not None:
        start_objects = predefine_queryset
    else:
        start_objects = model_class.objects

    if with_archived is None:
        queryset = start_objects.filter(query_filter).distinct()
    elif with_archived.lower() == 'all':
        query_filter &= Q(is_active__in=[True, False])
        queryset = start_objects.all(query_filter).distinct()
    elif with_archived.lower() == 'archived':
        query_filter &= Q(is_active=False)
        queryset = start_objects.all(query_filter).distinct()
    else:
        queryset = start_objects.filter(query_filter).distinct()

    if get_total_count:
        # https://code.djangoproject.com/ticket/30685
        total_count = start_objects.filter(query_filter).values("id").order_by().count()
    else:
        total_count = 0

    if limit is None or limit > settings.QUERY_LIMIT:
        limit = settings.QUERY_LIMIT

    if order is not None:
        order = [
            reduce(lambda string, pair: string.replace(pair[0], pair[1]),
                   (filter_map or {}).items(),
                   order_string) for order_string in order
        ]
        queryset = queryset.order_by(*order)

    if optimize_query is not None:
        queryset = optimize_query(queryset)

    sliced_queryset = get_slice(queryset, offset=offset, limit=limit)

    return total_count, sliced_queryset


def type_desc(type_, description):
    return type_
    # Not supported on python 3.8 only above 3.9
    # return Annotated[type_, strawberry.argument(description=description)]


def get_process_object(meta: dict, object_class: str) -> dict:
    return next(
        filter(lambda track: track.get('object', {}).get('class', '') == object_class, meta['processes']), {}
    )


def get_collection(gr_type: object, collection_name: str) -> object:
    if name := getattr(gr_type, "description_name", None):
        class_name = name
    else:
        class_name = gr_type.__name__

    meta_class = type(collection_name, (), {
        'total_count': strawberry.field(description=f'Total count of {class_name}'),
        'collection_items': strawberry.field(description=f'Filtered collection of {class_name}'),
    })
    meta_class.__annotations__ = {"total_count": int, "collection_items": List[gr_type]}

    return meta_class


# TODO remove generator
def paginated_field_generator(func, extra_args: Optional[Dict] = None, with_archived: Optional[bool] = False):
    description = {
        "ids": "Ids of objects",
        "filter": "Json filter",
        "order": "Order for objects",
        "offset": "Offset for objects",
        "limit": "Limit for objects",
        "with_archived": "Show archived objects or not"
    }

    def wrap_arg_in_param(args: ChainMap) -> List[Parameter]:
        return [Parameter(name=param_name,
                          annotation=param_annotation,
                          kind=Parameter.POSITIONAL_OR_KEYWORD,
                          default=None) for param_name, param_annotation in args.items()]

    signature_args = {
        'info': Info,
        'ids': type_desc(Optional[List[Optional[ID]]], description['ids']),
        'filter': type_desc(Optional[JSONString], description['filter']),
        'order': type_desc(Optional[List[Optional[str]]], description['order']),
        'offset': type_desc(Optional[int], description['offset']),
        'limit': type_desc(Optional[int], description['limit']),
    }

    if with_archived:
        signature_args['with_archived'] = type_desc(Optional[WithArchived], description["with_archived"])

    arg_chain_map = ChainMap(signature_args, extra_args or {})

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    wrapper.__signature__ = Signature(parameters=wrap_arg_in_param(arg_chain_map))

    # additional annotate because strawberry need it
    wrapper.__annotations__ = dict(arg_chain_map)

    return wrapper


def get_filters(filter_dict, filter_map=None):
    if filter_map:
        new_dict = {}
        for key in filter_dict.keys():
            new_key = reduce(lambda string, pair: string.replace(pair[0], pair[1]), filter_map.items(), key)
            new_dict[new_key] = filter_dict[key]
        filter_dict = new_dict
    query_filter = Q()
    for key, value in filter_dict.items():
        if key == 'and':
            query_filter &= get_filters(value, filter_map)
        elif key == 'or':
            or_filter = Q()
            for i in filter_dict['or']:
                or_filter |= get_filters(i, filter_map)
            query_filter &= or_filter
        else:
            query_filter &= Q(**{key: value})
    return query_filter


def get_slice(queryset, offset: int = 0, limit: int = settings.QUERY_LIMIT):
    if offset is not None:
        queryset = queryset[offset:]
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


class ApiError(GraphQLError):
    NOT_AUTHORIZED = 1
    WRONG_TOKEN = 2
    SERVICE_TOKEN_ERROR = 3
    WORKSPACE_NOT_FOUND = 4
    PASSWORDS_DO_NOT_MATCH = 5
    USER_EXISTS = 6
    INVALID_PASSWORD = 7
    INACTIVE_USER = 8

    def __init__(self, message, error_code=None, *args, **kwargs):
        self.error_code = error_code
        super().__init__(message, *args, **kwargs)


def get_token(info: Info) -> str:
    token = info.context.request.META.get('HTTP_TOKEN') or info.context.request.session.get('token')
    return str(token) if token is not None else None


def get_user(info: Info):
    return info.context.request.user


def get_workspace_id(info: Info) -> Optional[str]:
    workspace_id = info.context.request.GET.get('workspace') or info.context.request.GET.get('workspace_id') or \
                   info.context.request.META.get('workspace_id')

    return str(workspace_id) if workspace_id is not None else None


def get_license_id(info: Info) -> Optional[str]:
    license_id = info.context.request.GET.get('license') or info.context.request.GET.get('license_id') or \
                 info.context.request.META.get('license_id')

    return str(license_id) if license_id is not None else None


def get_content_type(content_type_header):
    # Content type may be like this "application/json;charset=UTF-8"
    return content_type_header.split(';')[0]


def graphql_request_extract(info, var):
    content_type = get_content_type(info.context.request.content_type)
    if content_type == 'application/json':
        return json.loads(info.context.request.body).get(var)
    return info.context.request.POST.get(var)


def extract_variables(info):
    return graphql_request_extract(info, 'variables')


def extract_query(info):
    return graphql_request_extract(info, 'query')


def utcnow_with_tz():
    """
    Return current utc time with timezone info
    :return: datetime
    """
    return datetime.now(pytz.utc)


def utcfromtimestamp_with_tz(timestamp: float):
    """
    Return datetime constructed from timestamp, with timezone info.
    :return: datetime
    """
    return datetime.fromtimestamp(timestamp, tz=pytz.utc)


def convert_datestr_to_date(value):
    if isinstance(value, str):
        return date_parser.parse(value)

    return value


class DatabaseSyncToAsync(SyncToAsync):
    """
    SyncToAsync version that cleans up old database connections when it exits.
    """

    def thread_handler(self, loop, *args, **kwargs):
        django.db.close_old_connections()
        try:
            return super().thread_handler(loop, *args, **kwargs)
        finally:
            django.db.close_old_connections()


# The class is TitleCased, but we want to encourage use as a callable/decorator
database_sync_to_async = DatabaseSyncToAsync


def elk_checker(func):
    def wrapper(*args, **kwargs):
        if settings.ENABLE_ELK:
            return func(*args, **kwargs)
        return
    return wrapper


class UsageAnalytics(threading.Thread):
    def __init__(self, operation: str, username: str, meta: dict = {}, space_id: Optional[str] = None):
        self.ok = True
        self.url = f'{settings.ELASTIC_URL_INT}/na-usage-analytics/_doc'
        self.data = {
            'ver': settings.PRODUCT_VERSION,
            'date': utcnow_with_tz().isoformat(),
            'user': username,
            'operation': operation,
            'meta': meta,
        }
        if space_id:
            self.data['space_id'] = space_id
        if not is_valid_json(self.data, usage_analytics_schema):
            print("Not valid data!", self.data)
            self.ok = False
        threading.Thread.__init__(self)

    @elk_checker
    def run(self):
        if self.ok:
            try:
                requests.post(self.url, headers=settings.ELASTIC_HEADERS_INT,
                              data=json.dumps(self.data), timeout=settings.USAGE_SEND_TIMEOUT)
            except requests.exceptions.ConnectTimeout:
                pass


class ActivityDocumentManager:
    @classmethod
    def __time_interval_format(cls, time_interval):
        try:
            return {
                'time_start': datetime.fromisoformat(time_interval[0]).isoformat(),
                'time_end': datetime.fromisoformat(time_interval[1]).isoformat()
            }
        except (TypeError, ValueError):
            return {
                'time_start': datetime.fromtimestamp(time_interval[0] / 1000.0, tz=timezone.utc).isoformat(),
                'time_end': datetime.fromtimestamp(time_interval[1] / 1000.0, tz=timezone.utc).isoformat()
            }

    @classmethod
    def get_process_data(cls, processes):
        process_data = {
            'age': None,
            'gender': None,
            'roi': [],
            'actions': {}
        }
        kind = set()
        direction = set()
        action_types = ["trigger_crossing"]
        for process in processes:
            if process['type'] not in ['track', 'emotion', 'action', 'attention']:
                continue

            if process['type'] == 'track':
                pr_object = process['object']
                if pr_object['class'] == 'face':
                    process_data['age'] = pr_object.get('age')
                    process_data['gender'] = pr_object.get('gender')
                    process_data.update(cls.__time_interval_format(process['time_interval']))
                elif pr_object['class'] == 'human':
                    process_data['person_id'] = pr_object['id']
                    process_data.update(cls.__time_interval_format(process['time_interval']))
            if process['type'] == 'action':
                pr_object = process['object']
                if pr_object['class'] == 'roi':
                    process_data['roi'].append({'id': pr_object.get('id'),
                                                'title': pr_object.get('name'),
                                                **cls.__time_interval_format(process['time_interval'])})
                elif process["action"] in action_types:
                    kind.add(process.get('action')),
                    direction.add(process.get('direction'))
            elif process['type'] == 'emotion':
                process_data[process['emotion']] = cls.__time_interval_format(process['time_interval'])
            elif process['type'] == 'attention' and process.get('time_interval', ''):
                process_data['watcher'] = cls.__time_interval_format(process['time_interval'])
        process_data['actions'].update({'kind': list(kind),
                                        'direction': list(direction)})
        return process_data


class AbstractManager(ABC):

    @staticmethod
    @abstractmethod
    def create():
        """
        Create managed object
        """
        pass

    @staticmethod
    @abstractmethod
    def delete():
        """
        Delete managed object
        """
        pass

    @staticmethod
    @abstractmethod
    def get():
        """
        Get managed object
        """
        pass


def validate_image(image: bytes):
    with BytesIO(image) as file:
        try:
            img_object = open_image(file)
        except UnidentifiedImageError:
            raise BadInputDataException("0xc69c44d4")

        if img_object.width > settings.MAX_IMAGE_WIDTH:
            raise BadInputDataException("0x006dd808")
        if img_object.height > settings.MAX_IMAGE_HEIGHT:
            raise BadInputDataException("0x006dd809")


def fixed_validate_image(image: bytes):
    with BytesIO(image) as file:
        try:
            img_object = open_image(file)
        except UnidentifiedImageError:
            raise BadInputDataException("0x6fd9bed7")

        if img_object.width > settings.MAX_IMAGE_WIDTH:
            raise BadInputDataException("0x006dd808")
        if img_object.height > settings.MAX_IMAGE_HEIGHT:
            raise BadInputDataException("0x006dd809")


def point_transform(face_info: dict) -> list:
    size = [face_info['bounding_box']['face_rectangle']['width'],
            face_info['bounding_box']['face_rectangle']['height']]
    left_pupil = face_info['bounding_box']['facial_landmarks'][7]
    right_pupil = face_info['bounding_box']['facial_landmarks'][10]
    for k, v in zip(left_pupil.keys(), size):
        left_pupil[k] = left_pupil[k] * v if left_pupil[k] < 1 else left_pupil[k]
    for k, v in zip(right_pupil.keys(), size):
        right_pupil[k] = right_pupil[k] * v if right_pupil[k] < 1 else right_pupil[k]
    return [{'leftPupil': left_pupil, 'rightPupil': right_pupil}]


def get_detect(image: str or bytes, templates_to_create: list,
               face_info: dict or None or list, request_id=None, is_anonymous=False) -> list:
    if isinstance(image, str):
        try:
            validator = URLValidator()
            validator(image)
            filename = os.path.basename(urlparse(image).path)
            # download_file(image, filename, settings.UNLIMITED_IMAGE_SIZE, settings.MAX_IMAGE_SIZE)
            with open(filename, 'rb') as f:
                image = f.read()
        except ValidationError:
            pass

    image = base64.standard_b64decode(image) if isinstance(image, str) else image
    validate_image(image)
    templates_fields = ','.join(templates_to_create)
    variables_declaration = '($file: Upload!, $hints: [EyesType!]!)' if face_info else '($file: Upload!)'
    variables_usage = '(upload: $file, hints: $hints)' if face_info else '(upload: $file)'
    query = f'''query {variables_declaration} {{
                   faces {variables_usage}{{
                       faceCrop {{x, y, width, height}},
                       sampleInfo,
                       processingInfo,
                       faceQuality,
                       {"" if is_anonymous else "image"},
                       {templates_fields}
                   }}
               }}'''
    variables = {'file': None}
    if face_info:
        hints = point_transform(face_info) if isinstance(face_info, dict) else face_info
        variables.update({'hints': hints})
    headers = {'X_REQUEST_ID': request_id}
    operations = json.dumps({'query': query, 'variables': variables})
    request_map = json.dumps({'0': ['variables.file']})

    tracing_context = get_current_tracing_context()
    headers.update(tracing_context)

    response = requests.post(
        f'{settings.PROCESSING_SERVICE_URL}/graphql',
        data={'operations': operations, 'map': request_map},
        files={'0': ('image', image, 'application/octet-stream')},
        headers=headers,
        timeout=settings.SERVICE_TIMEOUT)
    result = response.json()
    if result.get('errors') and result.get('errors')[0].get('message') == "No faces found":
        raise BadInputDataException('0x95bg42fd')
    elif result.get('errors'):
        raise Exception(result.get('errors')[0].get('message'))

    if not is_anonymous:
        for face in result['data']['faces']:
            face.update({'sourceImage': image})
    return result['data']['faces']


def face_processing_data_parser(faces: List[dict]) -> dict:
    def parse_face_info(face: dict, idx: int) -> dict:
        templates_to_create = []
        regex = re.compile('^template')
        for key in face.keys():
            if regex.search(key):
                templates_to_create.append(key)

        processing_info = json.loads(face['processingInfo'])

        keypoints = processing_info['keypoints']
        face_meta = processing_info['face_meta']

        emotions = {emotions_map.get(emotion['value'], emotion['value']): emotion['confidence']
                    for emotion in face_meta['emotions'] or []}

        keypoints = {keypoints_map.get(keypoint_key, keypoint_key): {
            'x': keypoint_value['proj'][0],
            'y': keypoint_value['proj'][1]
        } for keypoint_key, keypoint_value in keypoints.items()}

        return {
            'id': idx,
            'class': 'face',
            'templates': {f'${template_version}': face[template_version]
                          for template_version in templates_to_create},
            'bbox': processing_info['bbox'],
            '$cropImage': face.get('image'),
            'keypoints': keypoints,
            'age': face_meta['age']['value'],
            'emotions': emotions,
            'gender': face_meta['gender']['value'],
            'liveness': face_meta['liveness'],
            'angles': processing_info['angles'],
            'mask': face_meta['mask'],
            **({'quality': face['faceQuality']} if 'faceQuality' in face else {}),
        }

    source_image = faces[0].get('sourceImage')

    result = {
        '$image': base64.b64encode(source_image).decode() if source_image else None,
        f'objects@{SampleObjectsName.PROCESSING_CAPTURER}': [
            parse_face_info(face, idx) for idx, face in enumerate(faces, 1)
        ],
    }
    if (errors := json.loads(faces[0]['processingInfo']).get('errors')) is not None:
        result['errors'] = errors
    return result


def estimate_quality(template_version: str, best_shot_id: str) -> float:
    params = json.dumps({'template_version': template_version, 'best_shot_id': best_shot_id})
    try:
        tracing_context = get_current_tracing_context()

        response = requests.post(
            f'{settings.QUALITY_SERVICE_URL}/estimate/face',
            data=params,
            timeout=settings.SERVICE_TIMEOUT,
            headers=tracing_context
        )
        response.raise_for_status()
        return response.json().get('quality')
    except (ConnectionError, HTTPError) as ex:
        print(ex)
        return float('-inf')


def send_websocket_notifications(workspace_id: str, notification_info: dict):
    async_to_sync(get_channel_layer().group_send)(workspace_id,
                                                  {"type": "send_notifications",
                                                   "info": notification_info})


def load_image(path: str) -> Image:
    img = open_image(path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    return img


def _bbox_size(bbox):
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width, height


def crop_image_bbox(image, bbox) -> Image:
    width, height = image.size
    context_size = 0.2
    bbox = [bbox[0] * width, bbox[1] * height, bbox[2] * width, bbox[3] * height]

    for i in range(2):
        if round(bbox[i]) == round(bbox[i + 2]):
            bbox[i + 2] += 1
        elif bbox[i] > bbox[i + 2]:
            bbox[i], bbox[i + 2] = bbox[i + 2], bbox[i]

    bw, bh = _bbox_size(bbox.copy())

    pad_x = abs(bbox[0] - bbox[2]) * context_size
    pad_y = abs(bbox[1] - bbox[3]) * context_size
    bbox = [bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y]

    crop = image.crop(bbox)

    pad_size = 256
    img = ImageOps.pad(crop, (pad_size, pad_size), color='white')  # fix size of crop to avoid bbox blurring

    # scale bbox size due to pad function uses resize of image
    if bh > bw:
        scale = img.height / crop.height
    else:
        scale = img.width / crop.width
    bw *= scale
    bh *= scale

    return img


def extract_pupils(iter_object: object):
    if isinstance(iter_object, (EyesInput, PointInputType)):
        result = {}
        for item, value in vars(iter_object).items():
            result[item] = extract_pupils(value)
        return result
    else:
        return iter_object


def delete_none_from_dict(_dict):
    """Delete None values recursively from all of the dictionaries"""
    for key, value in list(_dict.items()):
        if isinstance(value, dict):
            delete_none_from_dict(value)
        elif value is None:
            del _dict[key]
        elif isinstance(value, list):
            for v_i in value:
                if isinstance(v_i, dict):
                    delete_none_from_dict(v_i)
    return _dict


def django_admin_inline_link(app_name: str, model_name: str, action: str, args: tuple, link_text: str):
    return format_html(
        '<a href="{}">{}</a>',
        reverse(f'admin:{app_name}_{model_name}_{action}', args=args),
        escape(link_text)
    )


class ModelMixin:
    class Queryset(models.QuerySet):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @atomic
        def delete(self):
            lock = self.select_for_update().all()
            items_count = int(lock.count())

            for item in lock:
                item.delete()

            return items_count, {getattr(self.model, '_meta').label: items_count}

        def with_archived(self):
            return self.filter(is_active__in=[True, False])

    class Manager(models.Manager):

        def all(self, query_filter: Q = Q(is_active=True)):
            if hasattr(self, 'core_filters'):
                query_filter &= Q(**self.core_filters)
            return self.__queryset(query_filter)

        def get_queryset(self):
            return self.__queryset(Q(is_active=True))

        def __queryset(self, query_filter: Q = Q()):
            queryset = ModelMixin.Queryset(model=self.model, using=self._db, hints=self._hints).filter(query_filter)
            return queryset

    @atomic
    def delete(self, using=None, keep_parents=False):
        signals.pre_delete.send(
            sender=type(self), instance=self
        )

        lock = type(self).objects.select_for_update().get(pk=self.pk)
        lock.is_active = False
        lock.save()

        signals.post_delete.send(
            sender=type(self), instance=self
        )


def camel(snake_str: str) -> str:
    """Convert string form camel to snake"""
    first, *others = snake_str.split('_')
    return ''.join([first.lower(), *map(str.title, others)])


def snake(camel_str: str) -> str:
    """Convert string form sale to camel"""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', camel_str).lower()
