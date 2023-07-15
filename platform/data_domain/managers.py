import copy
import io
import json
import math
import uuid
from collections import namedtuple
from dataclasses import dataclass, field

import bson
import base64
import datetime
from itertools import chain
from functools import partial
from typing import List, Tuple, Union, Optional

import jsonschema
import requests
from PIL import Image
from django.core.cache import cache
from django.db import transaction
from django.db.models import QuerySet

from data_domain.models import Sample, Activity, BlobMeta, Blob
from main import settings
from user_domain.models import Workspace
from platform_lib.validation.schemes import activation_schema, activity_meta_scheme, sample_meta_scheme
from platform_lib.exceptions import BadInputDataException
from platform_lib.utils import get_detect, face_processing_data_parser,\
    utcnow_with_tz, SampleObjectsName, camel, snake, fixed_validate_image
from platform_lib.managers import BaseProcessManager


class AgentDataManager:
    bsm_indicator = "$"

    @classmethod
    def decode(cls, data: bytes) -> Tuple[dict, bool]:
        """ Decodes abstract sample got over network
        :param data: "network sample" or raw_image
        :return: decoded sample and flag that specifies is input was a raw image or "network sample"
        """
        version_size = 1
        version = int.from_bytes(data[:version_size], byteorder='big')
        if version == 1:
            return bson.loads(data[version_size:]), False

        # assume that it is a raw image and pack it to bsm format
        return cls.__bsm('image', data), True

    @classmethod
    def __bsm(cls, key: str, blob: bytes):
        return {
            f'{cls.bsm_indicator}{key}': {
                'format': 'IMAGE',
                'blob': blob
            }
        }

    @classmethod
    def parse_extra(cls, data: dict):
        result = {k: v for k, v in data.items() if k not in ['prediction']}
        prediction = json.loads(data.get('prediction', '{}'))
        if 'objects' in prediction:
            result['objects'] = prediction['objects']
        return result

    @classmethod
    def validate_sample_meta(cls, meta: dict):
        try:
            jsonschema.validate(meta, activity_meta_scheme)
        except jsonschema.ValidationError:
            try:
                # bson doesn't decode numbers therefore try to decode meta data
                s = {k: cls.__json_decoder(v) for k, v in meta.items()}
                jsonschema.validate(s, activity_meta_scheme)
            except Exception:
                return False
        return True

    @classmethod
    def __json_decoder(cls, o: Union[list, tuple, str]):
        if isinstance(o, str):
            try:
                return int(o)
            except ValueError:
                try:
                    return float(o)
                except ValueError:
                    return o
        elif isinstance(o, dict):
            return {k: cls.__json_decoder(v) for k, v in o.items()}
        elif isinstance(o, (list, tuple)):
            return type(o)([cls.__json_decoder(v) for v in o])
        else:
            return o

    @classmethod
    def extract_bsms(cls, meta: dict, bsms: Optional[list] = None):
        """Extracts bsms values from meta and replaces it to id"""
        if bsms is None:
            bsms = []

        if isinstance(meta, dict):
            for k, v in meta.items():
                if k.startswith(cls.bsm_indicator):
                    unique_hash = str(uuid.uuid4())
                    bsms.append((k, v, unique_hash))
                    meta[k] = bsms.index((k, v, unique_hash))
                else:
                    meta[k], bsms = cls.extract_bsms(v, bsms)
        elif isinstance(meta, list):
            tmp_data = []
            for d in meta:
                m, bsms = cls.extract_bsms(d, bsms)
                tmp_data.append(m)
            return tmp_data, bsms

        return meta, bsms

    @classmethod
    def substitute_bsms(cls, meta: Union[list, dict, int, str], bsms: list, is_bsm: bool = False):
        """Substitute bsm info into meta. This method applies after extract method"""
        if isinstance(meta, dict):
            return {k: cls.substitute_bsms(v, bsms, k.startswith(AgentDataManager.bsm_indicator))
                    for k, v in meta.items()}
        elif isinstance(meta, list):
            return [cls.substitute_bsms(m, bsms) for m in meta]
        return bsms[meta] if is_bsm else meta


class OngoingManager:
    timeout = 10  # in seconds
    cache_set = partial(cache.set, timeout=timeout)

    @staticmethod
    def set_ongoings(ongoings: List[dict], workspace_id: str, camera_id: str) -> None:
        OngoingManager.cache_set(OngoingManager.__build_cache_key(workspace_id, camera_id), ongoings)

    @staticmethod
    def get_ongoings(workspace_id: str, location_id: str = '') -> List[dict]:
        cameras = Workspace.objects.get(id=workspace_id).cameras.all()
        if location_id:
            cameras = cameras.filter(camera_location__label_id=location_id)

        ongoings = [cache.get(OngoingManager.__build_cache_key(workspace_id, camera.id), []) for camera in cameras]
        return list(chain(*ongoings))

    @staticmethod
    def get_parent_process(ongoing: dict) -> dict:
        return next(filter(lambda proc: proc.get('object', {}).get('class', '') == 'human', ongoing['processes']), {})

    @staticmethod
    def __build_cache_key(workspace_id: str, camera_id: str) -> str:
        return f'ongoings:workspace:{workspace_id}:camera:{camera_id}'


class SampleManager:
    @staticmethod
    def __platform_object_key() -> str:
        return f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'

    @classmethod
    def create_sample(cls, workspace_id: str, sample_meta: dict) -> Sample:
        with transaction.atomic():
            sample = Sample.objects.create(workspace_id=workspace_id, meta=sample_meta)
        return sample

    @staticmethod
    def get_sample(workspace_id: str, sample_id: str) -> Sample:
        return Sample.objects.get(id=sample_id, workspace_id=workspace_id)

    @staticmethod
    def get_samples(workspace_id: str, sample_ids: List[str]) -> QuerySet:
        return Sample.objects.filter(id__in=sample_ids, workspace_id=workspace_id)

    @staticmethod
    def get_sample_ids(workspace_id: str, sample_ids: list) -> QuerySet:
        samples = Sample.objects.filter(workspace_id=workspace_id, id__in=sample_ids).values_list('id', flat=True)
        if samples.count() != len(set(sample_ids)):
            raise BadInputDataException("0x943b3c24")
        return samples

    @classmethod
    def update_sample_meta(cls, sample_id: Union[str, uuid.UUID], meta: dict) -> Sample:
        with transaction.atomic():
            locked_sample = Sample.objects.select_for_update().get(id=sample_id)
            locked_sample.meta.update(meta)
            locked_sample.save()
        return locked_sample

    @classmethod
    def update_face_object(cls, sample_meta: dict, new_info: dict):
        sample_meta.get(cls.__platform_object_key(), [{}])[0].update(new_info)

    @classmethod
    def get_template_id(cls, sample_meta: dict, template_version: str) -> Optional[str]:
        old_template = sample_meta.get(f'${template_version}', {}).get('id')
        new_template = sample_meta.get(cls.__platform_object_key(), [{}])[0] \
            .get('templates', {}).get(f'${template_version}', {}).get('id')

        return old_template or new_template

    @classmethod
    def get_raw_template(cls, sample_meta: dict, template_version: str) -> str:
        template_id = cls.get_template_id(sample_meta, template_version)

        blob = BlobMeta.objects.select_related('blob').get(id=template_id).blob.data.tobytes()
        return base64.standard_b64encode(blob).decode()

    @classmethod
    def get_image(cls, sample_meta: dict) -> Optional[bytes]:
        blob_meta = BlobMeta.objects.filter(id=sample_meta.get('$image', {}).get('id')).select_related('blob').first()
        if not blob_meta:
            return None
        return blob_meta.blob.data

    @classmethod
    def get_age(cls, sample_meta: dict) -> int:
        return sample_meta.get(cls.__platform_object_key(), [{}])[0].get('age')

    @classmethod
    def get_gender(cls, sample_meta: dict) -> str:
        return sample_meta.get(cls.__platform_object_key(), [{}])[0].get('gender')

    @classmethod
    def get_face_crop_id(cls, sample_meta: dict) -> str:
        best_shot = sample_meta.get('$best_shot', {}).get('id')
        face_crop = sample_meta.get(cls.__platform_object_key(), [{}])[0].get('$cropImage', {}).get('id')
        image = sample_meta.get('$image', {}).get('id')

        return best_shot or face_crop or image

    @classmethod
    def get_face_quality(cls, sample_meta: dict) -> float:
        new_quality = sample_meta.get(cls.__platform_object_key(), [{}])[0].get('quality')
        old_quality = sample_meta.get('quality')

        return old_quality or new_quality

    @staticmethod
    def __create_bsms(bsms: list, workspace_id: Union[str, uuid.UUID]) -> list:
        written_bsms = []
        for key, bsm, _ in bsms:
            try:
                blob = base64.b64decode(bsm)
            except TypeError:
                written_bsms.append(None)
                continue
            blob_type = None

            # TODO remove hardcoded bsm types
            binary_format = "NDARRAY"

            if key == "$cropImage" or key == "image":
                blob_type = "image"
                binary_format = "IMAGE"
            elif key.startswith(AgentDataManager.bsm_indicator):
                blob_type = key.replace(AgentDataManager.bsm_indicator, '')

            blob_obj = Blob.objects.create(data=blob)
            blob_meta = BlobMeta.objects.create(workspace_id=workspace_id, blob=blob_obj,
                                                meta={'type': blob_type, 'format': binary_format})

            written_bsms.append({'id': str(blob_meta.id)})

        return written_bsms

    @classmethod
    def create_blobs(cls, workspace_id: str, meta: dict) -> dict:
        with transaction.atomic():
            meta, bsms = AgentDataManager.extract_bsms(meta)
            created_bsms = cls.__create_bsms(bsms, workspace_id)
            meta = AgentDataManager.substitute_bsms(meta, created_bsms)
        return meta

    @staticmethod
    def process_image(image, template_version, eyes_list=None, request_id=None, is_anonymous=False) -> dict:
        faces = get_detect(image=image, face_info=eyes_list,
                           templates_to_create=[template_version],
                           request_id=request_id, is_anonymous=is_anonymous)
        if not faces:
            raise BadInputDataException('0x95bg42fd')

        return face_processing_data_parser(faces)

    @classmethod
    def delete(cls, workspace_id: str, sample_ids: list):
        with transaction.atomic():
            Sample.objects.select_for_update().filter(workspace_id=workspace_id, id__in=sample_ids).delete()

    @staticmethod
    def delete_samples(samples: QuerySet[Sample]) -> int:
        return samples.select_for_update().delete()[0]

    @staticmethod
    def change_meta_to_new(workspace_id: str, destination_sample_id: str, origin_sample_id: str) -> Sample:
        new_sample_meta = Sample.objects.get(workspace_id=workspace_id, id=origin_sample_id).meta
        with transaction.atomic():
            sample = Sample.objects.select_for_update().get(workspace_id=workspace_id, id=destination_sample_id)
            sample.meta = new_sample_meta
            sample.save()

        return sample


class BlobMetaManager:
    def __init__(self, blobmeta_id: str):
        self.id = blobmeta_id

    @property
    def blob(self):
        return BlobMeta.objects.get(id=self.id).blob


class ActivityManager:
    @staticmethod
    def get_activities(workspace: Workspace, activities_ids: list):
        activities = Activity.objects.select_for_update().filter(workspace=workspace, id__in=activities_ids)
        if activities.count() != len(set(activities_ids)):
            raise BadInputDataException("0x86bjl434")
        return activities

    @staticmethod
    def get_activity(workspace_id: str, activity_id: str) -> Activity:
        return Activity.objects.get(id=activity_id, workspace_id=workspace_id)

    @staticmethod
    def lock_activity(activity: Activity) -> Activity:
        return Activity.objects.select_for_update().get(id=activity.id)

    # TODO: Wrap getting different processes into one method
    # TODO: Maybe create ProcessManager in platform_lib
    @staticmethod
    def get_face_processes(activity: Activity) -> list:
        return list(filter(lambda track: track.get('object', {}).get('class', {}) == 'face',
                           activity.data['processes']))

    @staticmethod
    def get_body_processes(activity: Activity) -> list:
        return list(filter(lambda track: track.get('object', {}).get('class', {}) == 'body',
                           activity.data['processes']))

    @classmethod
    def get_best_shot_ids(cls, activity: Activity) -> list:
        if activity:
            face_processes = cls.get_face_processes(activity)
            return [process.get('$best_shot', {}).get('id') for process in face_processes]
        else:
            return [None]

    @classmethod
    def get_template_ids(cls, activity: Activity, template_version: str) -> List[str]:
        if activity:
            processes = cls.get_face_processes(activity)
            return [p.get('object', {}).get('embeddings', {}).get(f'${template_version}').get('id') for p in processes]
        return []

    @staticmethod
    def get_parent_process(activity: Activity) -> dict:
        return next(filter(lambda proc: proc.get('object', {}).get('class', '') == 'human',
                           activity.data['processes']), {})

    @classmethod
    def get_parent_time_interval(cls, activity: Activity) -> list:
        parent = cls.get_parent_process(activity)
        time_interval = parent.get('time_interval')
        return time_interval

    @staticmethod
    def isoformat_date(time):
        try:
            return datetime.datetime.fromisoformat(time).isoformat()
        except (TypeError, ValueError):
            return datetime.datetime.fromtimestamp(time / 1000.0, tz=datetime.timezone.utc).isoformat()

    @staticmethod
    def create_manual_activity(workspace_id: str, age: int, gender: str, template_blob_meta_id: str,
                               best_shot_blob_meta_id: str, template_version: str) -> Activity:
        human_track_id = str(uuid.uuid4())
        person_id = str(uuid.uuid4())
        time_interval = [
            utcnow_with_tz().isoformat(),
            utcnow_with_tz().isoformat(),
        ]
        data = {
            "manual": True,
            "processes": [
                {
                    "id": human_track_id,
                    "type": "track",
                    "object": {
                        "id": person_id,
                        "class": "human"
                    },
                    "time_interval": time_interval
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "track",
                    "object": {
                        "id": person_id,
                        "age": age,
                        "class": "face",
                        "gender": gender,
                        "embeddings": {
                            f"${template_version}": {
                                "id": template_blob_meta_id
                            }
                        }
                    },
                    "parent": human_track_id,
                    "$best_shot": {
                        "id": best_shot_blob_meta_id
                    },
                    "time_interval": time_interval
                },
            ],
        }
        with transaction.atomic():
            activity = Activity.objects.create(
                data=data,
                creation_date=utcnow_with_tz(),
                workspace_id=workspace_id
            )

        return activity

    @classmethod
    def delete(cls, workspace: Workspace, activities_ids: List):
        with transaction.atomic():
            cls.get_activities(workspace, activities_ids).delete()

    @classmethod
    def get_last_face_process(cls, activity: Activity) -> dict:
        face_processes = list(filter(lambda process: bool(process.get('$best_shot')), cls.get_face_processes(activity)))

        return sorted(face_processes,
                      key=lambda process: datetime.datetime.fromisoformat(process['time_interval'][0]),
                      reverse=True)[0] if face_processes else None

    @classmethod
    def get_last_body_process(cls, activity: Activity) -> dict:
        body_processes = list(filter(lambda process: bool(process.get('$best_shot')), cls.get_body_processes(activity)))

        return sorted(body_processes,
                      key=lambda process: datetime.datetime.fromisoformat(process['time_interval'][0]),
                      reverse=True)[0] if body_processes else None

    @classmethod
    def get_sample_id(cls, activity: Activity) -> Optional[str]:
        return (cls.get_face_processes(activity) or [{}])[0].get('sample_id')

    @classmethod
    def get_samples_ids(cls, activity: Activity) -> List[str]:
        face_processes = cls.get_face_processes(activity)
        return list(filter(None, map(lambda x: x.get("sample_id"), face_processes)))


class SampleEnricher:
    @dataclass(frozen=True, order=True)
    class FunctionContainer:
        sort_index: int = field(init=False, repr=False)
        func: callable = field(compare=False)
        func_name: str = field(init=False)
        weight: int

        def __post_init__(self):
            object.__setattr__(self, 'sort_index', self.weight)
            # for proper comparison
            object.__setattr__(self, 'func_name', self.func.__name__)

        def __str__(self):
            return f'{self.func_name}_{self.weight}'

    fitter_validation_scheme = {
        "type": "object",
        "required": ["$image", "objects"],
        "properties": {
            "$image": {
                "type": "string",
            },
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "class": {
                            "type": "string",
                            "enum": ["face", "body"]
                        },
                        "fitter": {
                            "type": "object",
                            "required": ["fitter_type", "keypoints", "left_eye", "right_eye"],
                            "properties": {
                                "fitter_type": {
                                    "type": "string",
                                    "enum": ["fda"]
                                },
                                "keypoints": {
                                    "type": "array",
                                    "minItems": 63,
                                    "maxItems": 63,
                                    "items": {"type": "number"}
                                },
                                "left_eye": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": 2,
                                    "items": {"type": "number"}
                                },
                                "right_eye": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": 2,
                                    "items": {"type": "number"}
                                },
                            },
                            "additionalProperties": False
                        }
                    },
                    "if": {
                        "properties": {"class": {"const": "face"}}
                    },
                    "then": {
                        "required": ["fitter"]
                    },
                },
                "minimum": 1
            }
        },
    }
    bbox_validation_scheme = {
        "type": "object",
        "required": ["$image", "objects"],
        "properties": {
            "$image": {
                "type": "string",
            },
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "class": {
                            "type": "string",
                            "enum": ["face", "body"]
                        },
                        "bbox": {
                            "type": "array",
                            "minItems": 4,
                            "maxItems": 4,
                            "items": {"type": "number"}
                        },
                    },
                    "if": {
                        "properties": {"class": {"const": "face"}}
                    },
                    "then": {
                        "required": ["bbox"]
                    },
                },
                "minimum": 1
            }
        },
    }

    to_camel = ["total_score",
                "is_sharp",
                "sharpness_score",
                "is_evenly_illuminated",
                "illumination_score",
                "no_flare",
                "is_left_eye_opened",
                "left_eye_openness_score",
                "is_right_eye_opened",
                "right_eye_openness_score",
                "is_rotation_acceptable",
                "max_rotation_deviation",
                "not_masked",
                "not_masked_score",
                "is_neutral_emotion",
                "neutral_emotion_score",
                "is_eyes_distance_acceptable",
                "eyes_distance",
                "is_margins_acceptable",
                "margin_outer_deviation",
                "margin_inner_deviation",
                "is_not_noisy",
                "noise_score",
                "watermark_score",
                "has_watermark",
                "dynamic_range_score",
                "is_dynamic_range_acceptable",
                "background_uniformity_score",
                "is_background_uniform"]

    to_snake = list(map(camel, to_camel))

    @classmethod
    def _convert_to_ias_format(cls, original_sample: dict) -> Tuple[dict, dict]:
        converted_sample = copy.deepcopy(original_sample)

        def recursion(original_sample_: Union[dict, list],
                      result_sample_: Union[dict, list],
                      previous_path: List[str],
                      blob_paths: dict):

            if isinstance(original_sample_, dict):
                for key, value in original_sample_.items():
                    if (key.startswith(BaseProcessManager.bsm_indicator) and isinstance(value, dict)):
                        new_path = copy.copy(previous_path)
                        new_path.append(key)
                        blob_paths['_'.join(new_path)] = value
                        result_sample_[key] = base64.b64encode(
                            BlobMeta.objects.select_related('blob').get(id=value['id']).blob.data
                        ).decode("utf-8")
                    elif isinstance(value, (list, dict)):
                        new_path = copy.copy(previous_path)
                        new_path.append(key)

                        recursion(value, result_sample_[key], new_path, blob_paths)

                    if key in cls.to_camel:
                        result_sample_[camel(key)] = result_sample_.pop(key)

            if isinstance(original_sample_, list):
                for i, sample_object in enumerate(original_sample_):
                    if isinstance(sample_object, dict) or isinstance(sample_object, list):
                        new_path = copy.copy(previous_path)
                        new_path.append(str(i))

                        recursion(sample_object, result_sample_[i], new_path, blob_paths)

        blob_paths = {}
        previous_path = []

        recursion(original_sample, converted_sample, previous_path, blob_paths)

        return blob_paths, converted_sample

    @classmethod
    def _convert_from_ias_format(cls, original_sample: dict, values_dict: dict):

        converted_sample = copy.deepcopy(original_sample)

        def recursion(original_sample_: Union[dict, list],
                      result_sample_: Union[dict, list],
                      previous_path: List[str],
                      values_dict: dict):

            if isinstance(original_sample_, dict):
                for key, value in original_sample_.items():
                    snake_key = None

                    if key in cls.to_snake:
                        snake_key = snake(key)
                        result_sample_[snake_key] = result_sample_.pop(key)

                    result_key = snake_key or key

                    if key.startswith(BaseProcessManager.bsm_indicator):
                        new_path = copy.copy(previous_path)

                        new_path.append(result_key)

                        key_path = '_'.join(new_path)
                        if key_path in values_dict:
                            result_sample_[result_key] = values_dict[key_path]

                    if isinstance(value, (list, dict)):
                        new_path = copy.copy(previous_path)
                        new_path.append(result_key)

                        recursion(value, result_sample_[result_key], new_path, values_dict)

            if isinstance(original_sample_, list):
                for i, sample_object in enumerate(original_sample_):
                    if isinstance(sample_object, dict) or isinstance(sample_object, list):
                        new_path = copy.copy(previous_path)
                        new_path.append(str(i))

                        recursion(sample_object, result_sample_[i], new_path, values_dict)

        previous_path = []

        recursion(original_sample, converted_sample, previous_path, values_dict)

        return converted_sample

    @staticmethod
    def _handle__image_api_response_error(response):
        if response.status_code >= 400:
            try:
                error_json = response.json()
            except ValueError:
                response.raise_for_status()

            if (detail := error_json.get('detail')) is not None:  # noqa
                raise Exception(detail)
            else:
                raise Exception(str(error_json))

    @classmethod
    def _handle_image(cls, image: Union[str, bytes], service_url: str, request_id: Optional[str] = None) -> dict:
        files = {
            'image': ('image.jpg', image)
        }
        headers = {'X_REQUEST_ID': request_id}

        response = requests.post(url=f"{service_url}/process/image", files=files, headers=headers)

        cls._handle__image_api_response_error(response)

        return response.json()

    @classmethod
    def _handle_sample(cls, sample_data: dict, service_url: str, request_id: Optional[str] = None) -> dict:
        headers = {'X_REQUEST_ID': request_id}

        response = requests.post(url=f"{service_url}/process/sample", json=sample_data, headers=headers)

        cls._handle__image_api_response_error(response)

        return response.json()

    def _send_request_based_on_source(self, service_url: str, sample_validation_cheme: dict = None):
        if self._sample is None:
            return self._handle_image(image=self._image, service_url=service_url, request_id=self.request_id)
        else:
            if sample_validation_cheme is not None:
                # Check if current sample data is enough for quality_estimator
                jsonschema.validate(self._sample, sample_validation_cheme)

            return self._handle_sample(sample_data=self._sample, service_url=service_url, request_id=self.request_id)

    def __init__(self,
                 image: Optional[Union[str, bytes]] = None,
                 sample_meta: Optional[dict] = None,
                 request_id: Optional[str] = None):
        self._sample = self._image = self._sample_indexes = None
        self._sample_blob_ids = {}
        self.request_id = request_id

        if (image is not None and sample_meta is not None) or (image is None and sample_meta is None):
            raise Exception('Wrong SampleEnricher input')

        if sample_meta is not None:
            jsonschema.validate(sample_meta, sample_meta_scheme)

            self._sample_indexes = {}

            decoded_img = (base64.standard_b64decode(sample_meta['$image'])
                           if isinstance(sample_meta['$image'], str) else sample_meta['$image'])
            fixed_validate_image(decoded_img)
            self._image = decoded_img

            self._sample_blob_ids, self._sample = self._convert_to_ias_format(sample_meta)

        if image is not None:
            decoded_img = base64.standard_b64decode(image) if isinstance(image, str) else image
            fixed_validate_image(decoded_img)

            self._image = decoded_img

    # Not use. Detect change bbox and face order
    def face_detector(self):
        result = self._send_request_based_on_source(settings.FACE_DETECTOR_SERVICE_URL)

        self._sample = result
        return self

    def face_fitter(self):
        result = self._send_request_based_on_source(settings.FACE_DETECTOR_FITTER_SERVICE_URL)

        image = Image.open(io.BytesIO(self._image))

        width, height = image.size

        for object in result['objects']:
            bbox = object['bbox']

            crop_margin = 0.3
            max_thumbnail_size = (300, 300)

            left_top_x = int(bbox[0] * width)
            left_top_y = int(bbox[1] * height)

            right_bottom_x = int(bbox[2] * width)
            right_bottom_y = int(bbox[3] * height)

            bbox_width = right_bottom_x - left_top_x
            bbox_height = right_bottom_y - left_top_y

            converted_left_x = int(max(left_top_x - bbox_width * crop_margin, 0))
            converted_left_y = int(max(left_top_y - bbox_height * crop_margin, 0))

            converted_right_x = int(min(right_bottom_x + bbox_width * crop_margin, width))
            converted_right_y = int(min(right_bottom_y + bbox_height * crop_margin, height))

            img_byte_arr = io.BytesIO()

            crop_img = image.crop(
                (converted_left_x, converted_left_y, converted_right_x, converted_right_y)
            )
            crop_img.thumbnail(max_thumbnail_size)
            crop_img.save(img_byte_arr, format='JPEG')

        self._sample = result
        return self

    def template_extractor(self):
        self._sample = self._send_request_based_on_source(settings.TEMPLATE_EXTRACTOR_SERVICE_URL)
        return self

    def liveness_estimator(self):
        self._sample = self._send_request_based_on_source(settings.LIVENESS_ESTIMATOR_SERVICE_URL)
        return self

    def emotion_estimator(self):
        self._sample = self._send_request_based_on_source(settings.EMOTION_ESTIMATOR_SERVICE_URL,
                                                          sample_validation_cheme=self.bbox_validation_scheme)
        return self

    def gender_estimator(self):
        self._sample = self._send_request_based_on_source(settings.GENDER_ESTIMATOR_SERVICE_URL,
                                                          sample_validation_cheme=self.bbox_validation_scheme)
        return self

    def mask_estimator(self):
        self._sample = self._send_request_based_on_source(settings.MASK_ESTIMATOR_SERVICE_URL,
                                                          sample_validation_cheme=self.bbox_validation_scheme)
        return self

    def age_estimator(self):
        self._sample = self._send_request_based_on_source(settings.AGE_ESTIMATOR_SERVICE_URL,
                                                          sample_validation_cheme=self.bbox_validation_scheme)
        return self

    def quality_estimator(self):
        if self._sample is None:
            raise Exception('Quality estimation requires detected face')

        # Check if current sample data is enough for quality_estimator
        jsonschema.validate(self._sample, self.fitter_validation_scheme)

        result = self._handle_sample(self._sample, settings.QUALITY_ASSESSMENT_SERVICE_URL, self.request_id)

        self._sample = result
        return self

    def get_result(self) -> dict:
        # result = copy.deepcopy(self._sample)

        # TODO [NIAS] wait for template format fix

        result = self._convert_from_ias_format(self._sample, self._sample_blob_ids)

        for object_ in result['objects']:
            if (template11v1000 := object_.get('$template')) is not None:
                object_['templates'] = {'$template11v1000': template11v1000}
                del object_['$template']
                del object_['template_size']

        jsonschema.validate(result, sample_meta_scheme)
        return result

    function_containers = (
        namedtuple("FunctionContainers", ['face_detector',
                                          'face_fitter',
                                          'template_extractor',
                                          'liveness_estimator',
                                          'gender_estimator',
                                          'emotion_estimator',
                                          'mask_estimator',
                                          'age_estimator',
                                          'quality_estimator'])
        (FunctionContainer(face_detector, 0),
         FunctionContainer(face_fitter, 0),
         FunctionContainer(template_extractor, 2),
         FunctionContainer(liveness_estimator, 0),
         FunctionContainer(gender_estimator, 1),
         FunctionContainer(emotion_estimator, 1),
         FunctionContainer(mask_estimator, 1),
         FunctionContainer(age_estimator, 1),
         FunctionContainer(quality_estimator, 1))
    )

    @classmethod
    def get_functions_by_fields(cls, fields: List[str]) -> List[callable]:
        function_mapping = {
            # ('id', 'class', 'confidence', 'bbox'): [cls.function_containers.face_detector],
            ('id',
             'class',
             'confidence',
             'bbox',
             'fitter',
             'angles',
             'cropImage'): [cls.function_containers.face_fitter],
            ('id', 'class', 'confidence', 'bbox', 'templates'): [cls.function_containers.template_extractor],
            ('id', 'class', 'confidence', 'bbox', 'liveness'): [cls.function_containers.liveness_estimator],
            ('id', 'class', 'gender'): [
                cls.function_containers.face_fitter, cls.function_containers.gender_estimator
            ],
            ('id', 'class', 'age'): [
                cls.function_containers.face_fitter, cls.function_containers.age_estimator
            ],
            ('id', 'class', 'mask'): [
                cls.function_containers.face_fitter, cls.function_containers.mask_estimator
            ],
            ('id', 'class', 'emotions'): [
                cls.function_containers.face_fitter, cls.function_containers.emotion_estimator
            ],
            ('id', 'class', 'bbox', 'quality'): [
                cls.function_containers.face_fitter, cls.function_containers.quality_estimator
            ],
        }

        field_function_containers = []

        for field_ in fields:
            for key in function_mapping.keys():
                if field_ in key:
                    field_function_containers = field_function_containers + function_mapping[key]
                    break

        field_function_containers = set(field_function_containers)

        print(f'Func: {[str(cont) for cont in field_function_containers]}')

        return [func_container.func for func_container in sorted(field_function_containers)]
