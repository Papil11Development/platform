import base64
from json import JSONDecodeError
from typing import List, Optional

import requests
import strawberry
from django.apps import apps
from django.conf import settings
from strawberry import ID
from strawberry.types import Info

from data_domain.api.utils import check_search_input_data, get_templates
from data_domain.api.v2.types import (ActivityFilter, ActivityOrdering,
                                      ActivityOutput, ActivitySearchType,
                                      MatchResult, SearchType)
from data_domain.managers import SampleManager
from data_domain.matcher import ActivityMatcherAPI, MatcherAPI
from data_domain.models import BlobMeta, Sample
from platform_lib.exceptions import BadInputDataException, InternalException
from platform_lib.strawberry_auth.permissions import (IsHaveAccess,
                                                      IsWorkspaceActive)
from platform_lib.types import JSON, CountList, CustomBinaryType, EyesInput
from platform_lib.utils import (SampleObjectsName, StrawberryDjangoCountList,
                                extract_pupils, get_workspace_id,
                                validate_image)

workspace_model = apps.get_model('user_domain', 'Workspace')


@strawberry.type
class Query:
    activities: CountList[ActivityOutput] = StrawberryDjangoCountList(permission_classes=[IsHaveAccess],
                                                                      description="Get a list of activities",
                                                                      filters=ActivityFilter,
                                                                      order=ActivityOrdering,
                                                                      pagination=True)

    @strawberry.field(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                      description="Compare the sample from the picture/sampleData/sampleID with the sample in the DB")
    def verify(self, info: Info, target_sample_id: ID, source_sample_id: Optional[ID] = None,
               source_sample_data: Optional[JSON] = None, source_image: Optional[CustomBinaryType] = None) \
            -> MatchResult:

        if sum(map(bool, [source_sample_id, source_sample_data, source_image])) != 1:
            raise BadInputDataException("0x963fb254")

        workspace_id = get_workspace_id(info=info)
        objects_key = f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'
        template_version = workspace_model.objects.get(id=workspace_id).config.get(
            'template_version', settings.DEFAULT_TEMPLATES_VERSION
        )

        # GET TEMPLATE BLOBS
        target_sample = Sample.objects.get(id=target_sample_id)
        target_template_id = SampleManager.get_template_id(target_sample.meta, template_version)
        target_blob = BlobMeta.objects.select_related('blob').get(id=target_template_id).blob.data
        target_template = base64.standard_b64encode(target_blob.tobytes()).decode()
        match_templates = [target_template]

        if source_sample_id:
            source_sample = Sample.objects.get(id=source_sample_id)
            source_template_id = SampleManager.get_template_id(source_sample.meta, template_version)
            source_blob = BlobMeta.objects.select_related('blob').get(id=source_template_id).blob.data
            match_templates.append(base64.standard_b64encode(source_blob.tobytes()).decode())

        elif source_sample_data:
            source_sample_data = source_sample_data.get('data') or source_sample_data  # if input with data or not
            source_template = source_sample_data[objects_key][0]['templates'][f"${template_version}"]
            try:
                template_id = source_template.get('id')
                source_blob = BlobMeta.objects.select_related('blob').get(id=template_id).blob.data.tobytes()
                match_templates.append(base64.standard_b64encode(source_blob).decode())
            except AttributeError:
                # source_template is already base64
                match_templates.append(source_template)

        else:
            validate_image(source_image)
            processing_result = SampleManager.process_image(image=source_image, template_version=template_version)
            template = processing_result[objects_key][0]['templates'][f"${template_version}"]
            match_templates.append(template)

        assert len(match_templates) == 2, "One or both samples have an invalid format"

        proc_objects = []
        for templ in match_templates:
            proc_objects.append({"$template": templ, "class": "face"})

        response = requests.post(
            f'{settings.VERIFY_MATCHER_SERVICE_URL}/process/sample',
            json={"objects": proc_objects})

        try:
            result_json = response.json()
        except (ValueError, TypeError, JSONDecodeError):
            raise InternalException('0x176cbb31', response.content)

        if response.status_code != 200:
            if (detail := result_json.get('detail')) is not None:
                err = detail
            else:
                err = result_json

            raise InternalException('0x176cbb31', err)

        return MatchResult(**result_json['verification'])

    @strawberry.field(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                      description="Search similar people in a workspace based on images, sample data, or sample IDs" +
                                  (". If a found human doesn't have a profile in system, profile output will be 'null'."
                      if not settings.ENABLE_PROFILE_AUTOGENERATION else ''))
    def search(self, info: Info,
               source_sample_ids: Optional[List[ID]] = None,
               source_sample_data: Optional[JSON] = None,
               source_image: Optional[CustomBinaryType] = None,
               scope: Optional[ID] = None,
               confidence_threshold: Optional[float] = 0.0,
               max_num_of_candidates_returned: Optional[int] = 5) -> List[SearchType]:

        check_search_input_data(**locals())

        workspace_id = get_workspace_id(info=info)
        index_key = scope or workspace_id
        template_version = workspace_model.objects.get(id=workspace_id).config.get('template_version',
                                                                                   settings.DEFAULT_TEMPLATES_VERSION)
        templates = get_templates(template_version, source_sample_ids, source_sample_data, source_image)
        objects_key = f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'
        template_version = workspace_model.objects.get(id=workspace_id).config.get(
            'template_version', settings.DEFAULT_TEMPLATES_VERSION
        )

        if source_sample_ids:
            samples = sorted(Sample.objects.filter(id__in=source_sample_ids),
                             key=lambda x: source_sample_ids.index(str(x.id)))
            template_ids = [SampleManager.get_template_id(sample.meta, template_version) for sample in samples]
            templates_meta = sorted(BlobMeta.objects.select_related('blob').filter(id__in=template_ids),
                                    key=lambda x: template_ids.index(str(x.id)))
            templates = [base64.standard_b64encode(template_meta.blob.data.tobytes()).decode() for
                         template_meta in templates_meta]

        elif source_sample_data:
            source_sample_data = source_sample_data.get('data') or source_sample_data  # if input with data or not
            source_templates = [face['templates'][f"${template_version}"] for
                                face in source_sample_data[objects_key]]
            try:
                template_ids = [template.get('id') for template in source_templates]
                templates_meta = sorted(BlobMeta.objects.select_related('blob').filter(id__in=template_ids),
                                        key=lambda x: template_ids.index(str(x.id)))
                templates = [base64.standard_b64encode(template_meta.tobytes()).decode()
                             for template_meta in templates_meta]
            except AttributeError:
                templates = source_templates

        else:
            validate_image(source_image)
            processing_result = SampleManager.process_image(image=source_image, template_version=template_version)
            templates = [face['templates'][f"${template_version}"] for face in processing_result[objects_key]]

        index_key = scope or workspace_id

        search_results = MatcherAPI.search(index_key,
                                           template_version,
                                           templates,
                                           nearest_count=max_num_of_candidates_returned,
                                           score=confidence_threshold)

        return search_results  # noqa

    @strawberry.field(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                      description="Search similar activity in a workspace based on images, sample data, or sample IDs")
    def search_in_activities(self, info: Info,
                             source_sample_ids: Optional[List[ID]] = None,
                             source_sample_data: Optional[JSON] = None,
                             source_image: Optional[CustomBinaryType] = None,
                             confidence_threshold: Optional[float] = 0.0,
                             max_num_of_candidates_returned: Optional[int] = 5) -> List[ActivitySearchType]:

        check_search_input_data(**locals())

        workspace_id = get_workspace_id(info=info)
        template_version = workspace_model.objects.get(id=workspace_id).config.get('template_version',
                                                                                   settings.DEFAULT_TEMPLATES_VERSION)
        templates = get_templates(template_version, source_sample_ids, source_sample_data, source_image)

        search_results = ActivityMatcherAPI.search(workspace_id,
                                                   template_version,
                                                   templates,
                                                   nearest_count=max_num_of_candidates_returned,
                                                   score=confidence_threshold)

        return search_results  # noqa

    @strawberry.field(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Detect faces on the image")
    def detect(self, info: Info, image: CustomBinaryType, pupils: Optional[List[EyesInput]] = None) -> JSON:
        validate_image(image)
        workspace_id = get_workspace_id(info=info)
        template_version = workspace_model.objects.get(id=workspace_id).config.get('template_version',
                                                                                   settings.DEFAULT_TEMPLATES_VERSION)

        if pupils:
            pupils = [extract_pupils(pupil) for pupil in pupils]

        result = SampleManager.process_image(image, template_version, pupils)
        return result
