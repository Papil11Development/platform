import json
import math
import uuid
import bson
import base64
import datetime
from itertools import chain
from functools import partial
from typing import List, Tuple, Union, Optional


import jsonschema
from django.core.cache import cache
from django.db import transaction
from django.db.models import QuerySet

from data_domain.models import Sample, Activity, BlobMeta, Blob
from user_domain.models import Workspace
from platform_lib.validation.schemes import sample_meta_scheme
from platform_lib.exceptions import BadInputDataException
from platform_lib.utils import get_detect, face_processing_data_parser, utcnow_with_tz, SampleObjectsName, \
    estimate_quality


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
            jsonschema.validate(meta, sample_meta_scheme)
        except jsonschema.ValidationError:
            try:
                # bson doesn't decode numbers therefore try to decode meta data
                s = {k: cls.__json_decoder(v) for k, v in meta.items()}
                jsonschema.validate(s, sample_meta_scheme)
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
    def get_template_id(cls, sample_meta: dict, template_version: str) -> str:
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
    def update_sample_quality(cls,
                              sample_id: Union[str, uuid.UUID],
                              template_version: str) -> Tuple[bool, Sample, float]:
        with transaction.atomic():
            sample = Sample.objects.select_for_update().get(id=sample_id)
            quality = estimate_quality(template_version, cls.get_face_crop_id(sample.meta))

            if math.isinf(quality):
                return False, sample, quality

            cls.update_face_object(sample.meta, {'quality': quality})
            sample.save()

        return True, sample, quality

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
    def process_image(image, template_version, eyes_list=None, request_id=None) -> dict:
        faces = get_detect(image=image, face_info=eyes_list,
                           templates_to_create=[template_version],
                           request_id=request_id)
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
    def get_sample(workspace_id: str, sample_id: str) -> Sample:
        return Sample.objects.get(id=sample_id, workspace_id=workspace_id)

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
    def get_sample_id(cls, activity: Activity) -> str:
        return (cls.get_face_processes(activity) or [{}])[0].get('sample_id')

    @classmethod
    def get_samples_ids(cls, activity: Activity) -> List[str]:
        face_processes = cls.get_face_processes(activity)
        return list(filter(None, map(lambda x: x.get("sample_id"), face_processes)))
