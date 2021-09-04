import base64
import math
from typing import List, Optional

import strawberry
from django.apps import apps
from django.conf import settings
from django.db import transaction
from strawberry.types import Info

from data_domain.api.v2.types import SampleOutput
from data_domain.managers import SampleManager, SampleObjectsName
from data_domain.models import Sample, BlobMeta
from platform_lib.exceptions import BadInputDataException
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from platform_lib.types import CustomBinaryType, JSON, EyesInput
from platform_lib.utils import get_workspace_id, validate_image, estimate_quality, extract_pupils

workspace_model = apps.get_model('user_domain', 'Workspace')


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Create a sample object from an image or raw sampleData")
    def create_sample(self, info: Info, image: Optional[CustomBinaryType] = None,
                      sample_data: Optional[JSON] = None,
                      pupils: Optional[List[EyesInput]] = None,
                      anonymous_mode: Optional[bool] = False) -> List[SampleOutput]:

        if sum(map(bool, [image, sample_data])) != 1:
            raise BadInputDataException("0xnf5825dh")

        workspace_id = get_workspace_id(info=info)
        objects_key = f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'
        template_version = workspace_model.objects.get(id=workspace_id).config.get('template_version',
                                                                                   settings.DEFAULT_TEMPLATES_VERSION)
        if pupils:
            pupils = [extract_pupils(pupil) for pupil in pupils]

        samples = []

        if image:
            validate_image(image)
            sample_data = SampleManager.process_image(image, template_version, pupils)
        elif sample_data:
            sample_data = sample_data.get('data') or sample_data  # if input with data or not

        if anonymous_mode:
            sample_data.update({'$image': None})
            for face in sample_data[objects_key]:
                face.update({'$cropImage': None})
        else:
            validate_image(base64.standard_b64decode(sample_data.get('$image')))

        face_meta_with_ids = SampleManager.create_blobs(workspace_id, sample_data)
        for face_meta in face_meta_with_ids[objects_key]:
            with transaction.atomic():
                sample = SampleManager.create_sample(workspace_id=workspace_id,
                                                     sample_meta={'$image': face_meta_with_ids['$image'],
                                                                  objects_key: [face_meta]})

                template_blob_meta_id = face_meta['templates'][f'${template_version}']['id']

                template_blob_meta = BlobMeta.objects.select_for_update().get(id=template_blob_meta_id)
                template_blob_meta.meta.update({'sample_id': str(sample.id)})
                template_blob_meta.save()

            if not anonymous_mode:
                _, sample, _ = SampleManager.update_sample_quality(str(sample.id), template_version)

            samples.append(sample)

        return samples
