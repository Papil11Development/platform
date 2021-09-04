import json
import base64

from enum import Enum
from typing import Any, NewType, TypeVar, Generic, Optional, List
from collections import namedtuple

import graphql
from graphql.language import ast
import strawberry
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError


class ElasticAction(str, Enum):
    push = 'push'
    drop = 'drop'


@strawberry.type(description="Result of mutation work")
class MutationResult:
    ok: bool = strawberry.field(description="Indicator of mutation success")


@strawberry.enum
class WithArchived(Enum):
    archived = 'archived'
    all = 'all'


JSONString = strawberry.scalar(
    NewType("JSONString", Any),
    description="Type that represent json in string format",
    serialize=lambda v: json.dumps(v),
    parse_value=lambda v: json.loads(v),
    parse_literal=graphql.utilities.value_from_ast_untyped,
)

# TODO: Will be removed after strawberry update
JSON = strawberry.scalar(
    NewType("JSON", object),
    description="The `JSON` scalar type represents JSON values as specified by ECMA-404",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)

CustomBinaryType = strawberry.scalar(
    NewType("CustomBinaryType", bytes),
    description="Type that represent binary information",
    serialize=lambda v: serialize_custom_binary_type(v),
    parse_value=lambda v: base64.b64decode(v),
    parse_literal=lambda v: parse_literal_custom_binary_type(v)
)


def serialize_custom_binary_type(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, list):
        return base64.b64encode(bytes(value)).decode()
    return base64.b64encode(value.tobytes()).decode()


def parse_literal_custom_binary_type(node):
    if isinstance(node, ast.StringValueNode):
        try:
            validator = URLValidator()
            validator(node.value)
            return node.value
        except ValidationError:
            return base64.b64decode(node.value)


@strawberry.type
class PointType:
    x: float
    y: float


@strawberry.input
class PointInputType:
    x: float
    y: float


@strawberry.input(description="Tuple of eye pupil coordinates")
class EyesInput:
    leftPupil: PointInputType = strawberry.field(description="Coordinates of left eye pupil")
    rightPupil: PointInputType = strawberry.field(description="Coordinates of right eye pupil")


T = TypeVar("T")


@strawberry.input
class FilterLookupCustom(Generic[T]):
    exact: Optional[T] = strawberry.field(default=None, description="Filtered value equals to")
    i_exact: Optional[T] = strawberry.field(default=None, description="'i_exact' is case insensitive exact")
    contains: Optional[str] = strawberry.field(default=None, description="Filtered value contains")
    i_contains: Optional[str] = strawberry.field(default=None, description="'i_contains' contains case insensitive")
    in_list: Optional[List[T]] = strawberry.field(default=None, description="Filtered value is in the list")
    gt: Optional[T] = strawberry.field(default=None, description="Filtered value is greater than (>)")
    gte: Optional[T] = strawberry.field(default=None, description="Filtered value is greater or equals to (>=)")
    lt: Optional[T] = strawberry.field(default=None, description="Filtered value is less than (<)")
    lte: Optional[T] = strawberry.field(default=None, description="Filtered value is less or equals to (<=)")
    starts_with: Optional[str] = strawberry.field(default=None, description="Filtered value starts with")
    i_starts_with: Optional[str] = strawberry.field(
        default=None,
        description="'i_starts_with' starts with case insensitive"
    )
    ends_with: Optional[str] = strawberry.field(default=None, description="Filtered value ends with")
    i_ends_with: Optional[str] = strawberry.field(default=None, description="'i_ends_with' ends with case insensitive")
    range: Optional[List[T]] = strawberry.field(default=None, description="Filtered value is in the range")
    is_null: Optional[bool] = strawberry.field(default=None, description="Filtered value is null")
    regex: Optional[str] = strawberry.field(
        default=None,
        description="Filtered value corresponds to the regex"
    )
    i_regex: Optional[str] = strawberry.field(default=None, description="'i_regex' is case insensitive regex")


@strawberry.type
class CountList(Generic[T]):
    total_count: int
    collection_items: List[T]


emotions_map = {'NEUTRAL': 'neutral', 'ANGRY': 'angry', 'HAPPY': 'happy', 'SURPRISE': 'surprised'}

keypoints_map = {'.0': 'left_eye_brow_left',
                 '.1': 'left_eye_brow_up',
                 '.2': 'left_eye_brow_right',
                 '.3': 'right_eye_brow_left',
                 '.4': 'right_eye_brow_up',
                 '.5': 'right_eye_brow_right',
                 '.6': 'left_eye_left',
                 '.7': 'left_pupil',
                 '.8': 'left_eye_right',
                 '.9': 'right_eye_left',
                 '.10': 'right_pupil',
                 '.11': 'right_eye_right',
                 '.12': 'left_ear_bottom',
                 '.13': 'nose_left',
                 '.14': 'nose',
                 '.15': 'nose_right',
                 '.16': 'right_ear_bottom',
                 '.17': 'mouth_left',
                 '.18': 'mouth',
                 '.19': 'mouth_right',
                 '.20': 'chin'}

Collection = namedtuple("Collection", ["total_count", "collection_items"])
