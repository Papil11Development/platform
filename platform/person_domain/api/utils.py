from typing import Tuple, Optional

from main.settings import DEFAULT_FAR_THRESHOLD_VALUE, MATCHRESULT_BEST_QUALITY_THRESHOLD
from platform_lib.exceptions import BadInputDataException
from platform_lib.types import CustomBinaryType
from platform_lib.utils import SampleObjectsName

from django.db.transaction import atomic
from django.db.models import QuerySet, Prefetch
from django.apps import apps

from person_domain.models import Person, Profile
from person_domain.managers import ProfileManager
from person_domain.api.v2.types import ProfileInput

from data_domain.models import Sample
from data_domain.managers import SampleManager
from user_domain.models import Workspace


def get_search_person(best_shot_quality: float, result: dict):
    if not best_shot_quality > MATCHRESULT_BEST_QUALITY_THRESHOLD:
        raise BadInputDataException('0x86bd49dh')
    person = None
    search_result = result.get('searchResult', [])

    if search_result and search_result[0].get('matchResult', {}).get('faR', 1) < DEFAULT_FAR_THRESHOLD_VALUE:
        person = Person.objects.select_related('profile').get(id=search_result[0].get('personId'))

    return person


def check_face_quality(best_shot_quality: float):
    if not best_shot_quality > MATCHRESULT_BEST_QUALITY_THRESHOLD:
        raise BadInputDataException('0x86bd49dh')


def create_profile_info(data: ProfileInput,
                        workspace: Workspace,
                        p_sample: Optional[Sample] = None,
                        blob_meta_id: Optional[str] = None) -> Tuple[Profile, Person]:

    sample_ids = None
    profile_info = data.info

    if p_sample is not None:
        profile_info = {
            'age': SampleManager.get_age(p_sample.meta),
            'gender': SampleManager.get_gender(p_sample.meta).upper(),
            'main_sample_id': str(p_sample.id),
            'avatar_id': blob_meta_id,
            **data.info
        }

        sample_ids = [str(p_sample.id)]

    created_profile, created_person = ProfileManager.create_with_person(workspace=workspace,
                                                                        info=profile_info,
                                                                        label_ids=data.profile_group_ids,
                                                                        sample_ids=sample_ids)

    return created_profile, created_person


def handle_image(img: CustomBinaryType, template_version: str, workspace_id: str) -> Tuple[Sample, float]:
    with atomic():
        objects_key = f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'

        processing_result = SampleManager.process_image(image=img, template_version=template_version)

        if len(processing_result[objects_key]) > 1:
            raise BadInputDataException('0x35vd45ms')

        # raw_template = processing_result[objects_key][0]['templates'][f"${template_version}"]

        processing_result_with_ids = SampleManager.create_blobs(workspace_id, meta=processing_result)
        face_meta_with_ids = processing_result_with_ids[objects_key][0]

        created_sample = SampleManager.create_sample(
            workspace_id=workspace_id,
            sample_meta={
                '$image': processing_result_with_ids['$image'],
                objects_key: [face_meta_with_ids]
            })

    _, created_sample, quality = SampleManager.update_sample_quality(created_sample.id, template_version)

    try:
        check_face_quality(quality)
    except BadInputDataException:
        SampleManager.delete(workspace_id, [created_sample.id])
        raise

    return created_sample, quality


def optimizer_profile_queryset(queryset: QuerySet):
    activities = apps.get_model('data_domain', 'Activity')
    return queryset.select_related('person').prefetch_related(
            'profile_groups',
            'samples',
            Prefetch('person__activities', queryset=activities.objects.order_by('creation_date'))
            ).distinct()
