import copy
import json
import os
import time
import uuid
from typing import Tuple, Dict, Union, Any, List

from celery import shared_task
from django.apps import apps
from django.db import connection
from django.db.models import Q

from person_domain.models import Person
from platform_lib.utils import get_process_object
from main.settings import DEFAULT_TEMPLATES_VERSION


@shared_task
def duplicate_persons(access_id: Union[str, uuid.UUID],
                      duplicate_count: int,
                      person_ids: List[str],
                      fast_mode: bool = False):
    blob_model = apps.get_model('data_domain', 'Blob')
    blob_meta_model = apps.get_model('data_domain', 'BlobMeta')
    access_model = apps.get_model('user_domain', 'Access')
    sample_model = apps.get_model('data_domain', 'Sample')

    sql_id_mapping = {
        "$best_shot": "[{}_best_shot]",
        f"${DEFAULT_TEMPLATES_VERSION}": "[{}_template]",
        "$image": "[{}_image]",
        "$cropImage": "[{}_crop_image]",
        "$binary_image": "[{}_binary_image]",
        "$v1": "[{}_v1]",
        "main_sample_id": "[main_sample_id]",
        "activity_id": "[activity_id]",
        "avatar_id": "[avatar_id]",
    }

    def get_profile_info_without_id(info: dict) -> Union[Dict, Any]:
        local_info = copy.deepcopy(info)
        main_sample_id_key = "main_sample_id"
        sample_id = local_info[main_sample_id_key]
        local_info[main_sample_id_key] = sql_id_mapping[main_sample_id_key]

        avatar_id_key = "avatar_id"
        if local_info.get(avatar_id_key):
            local_info[avatar_id_key] = sql_id_mapping[avatar_id_key]

        return local_info, sample_id

    def prepare_blob_meta(meta: Union[Dict, None]) -> Union[str, None]:
        if meta is None:
            return None

        local_meta = copy.deepcopy(meta)
        local_meta["activity_id"] = sql_id_mapping["activity_id"]

        return json.dumps(local_meta)

    def extract_bsm_info_from_base_object(blob_meta_id: Union[str, uuid.UUID]) -> Tuple[Dict, Dict]:
        blob_meta = blob_meta_model.objects.get(id=blob_meta_id)
        blob = blob_model.objects.get(id=blob_meta.blob_id)

        return blob_meta.meta, blob.data

    def substitute_id_in_obj(data: dict, object_name: str, fast_mode: bool = False) -> Tuple[Dict, Dict]:
        blob_meta_infos = {}

        if object_name in ("face", "human"):
            data["object"]["id"] = "[person_id]"

        if object_name == "sample":
            data["person_id"] = "[person_id]"

        if fast_mode:
            return data, {}

        def extract_bsms(element):
            nonlocal blob_meta_infos

            if isinstance(element, dict):
                for key, value in element.items():
                    if key.startswith("$"):
                        if not sql_id_mapping.get(key):
                            print('This key not present:', f'"{key}"')
                            continue
                        try:
                            blob_meta_infos[key] = extract_bsm_info_from_base_object(element[key]["id"])
                        except blob_meta_model.DoesNotExist:
                            blob_meta_infos[key] = (None, None)
                        element[key]["id"] = sql_id_mapping[key].format(object_name)
                    else:
                        extract_bsms(value)

            elif isinstance(element, list):
                for value in element:
                    extract_bsms(value)

        extract_bsms(data)

        return data, blob_meta_infos

    print("Duplicate person task started")

    time1 = time.time()

    access = access_model.objects.get(id=access_id)
    workspace = access.workspace

    person_filter = Q(workspace=workspace)

    if person_ids is not None:
        person_filter &= Q(id__in=person_ids)

    persons = Person.objects.filter(person_filter).select_related('profile')

    with open(os.path.join(os.path.dirname(__file__), 'qa_requests/duplicate_person.sql'), 'rt') as duplicate_sql:
        duplicate_sql_command = duplicate_sql.read()

    for person in persons:

        profile = person.profile
        activity = person.activities.first()

        profile_info, sample_id = get_profile_info_without_id(profile.info)

        sample = sample_model.objects.get(id=sample_id)

        new_sample_meta = copy.deepcopy(sample.meta)

        _, sample_blobs_infos = substitute_id_in_obj(
            new_sample_meta, "sample", fast_mode
        )

        if activity is not None:
            copied_activity_data = copy.deepcopy(activity.data)

            face_process, face_blob_infos = substitute_id_in_obj(
                get_process_object(copied_activity_data, "face"), "face", fast_mode
            )
            body_process, body_blob_infos = substitute_id_in_obj(
                get_process_object(copied_activity_data, "body"), "body", fast_mode
            )
            human_process, _ = substitute_id_in_obj(
                get_process_object(copied_activity_data, "human"), "human", fast_mode
            )

            processes = [human_process, face_process]

            if body_process:
                processes.append(body_process)

            new_activity_data = json.dumps({"processes": processes})
        else:
            new_activity_data, face_blob_infos, body_blob_infos = None, {}, {}

        face_keys = ['$binary_image']
        body_keys = ['$v1', '$best_shot']
        sample_keys = ['$image', '$cropImage', f'${DEFAULT_TEMPLATES_VERSION}']

        if fast_mode:
            blob_args = [None] * len(face_keys + body_keys + sample_keys)
        else:
            blob_args = []

            for keys, blobs_infos in [
                (face_keys, face_blob_infos),
                (body_keys, body_blob_infos),
                (sample_keys, sample_blobs_infos)
            ]:
                for key in keys:
                    # For null value in sql statement if blob not presented
                    blob_tuple = blobs_infos.get(key)
                    if blob_tuple is None:
                        blob_args += [None, None]
                    else:
                        blob_args += [prepare_blob_meta(blob_tuple[0]), blob_tuple[1]]

        groups = str(list(str(group.id) for group in profile.profile_groups.all()))
        group_ids = groups.replace('[', '{').replace(']', '}').replace('\'', '\"')

        BLOCK_SIZE = 1000
        blocks = [BLOCK_SIZE] * (duplicate_count // BLOCK_SIZE)
        if duplicate_count % BLOCK_SIZE:
            blocks += [duplicate_count % BLOCK_SIZE]

        cursor = connection.cursor()
        for batch_size in blocks:
            param_tuple = (
                workspace.id,
                # Person info
                json.dumps(profile_info),
                group_ids,

                # Activity data
                new_activity_data,
                getattr(activity, 'camera_id', None),

                # Blob data
                *blob_args,

                # Sample data
                json.dumps(new_sample_meta),
                batch_size,
                fast_mode
            )
            cursor.execute(duplicate_sql_command, param_tuple)
            connection.commit()
    connection.close()

    print(f"Duplicate person task finished in time: {time.time() - time1}")
