import os
import math
from typing import List, Optional

from user_domain.models import Workspace  # noqa
from person_domain.managers import PersonManager, ProfileManager
from person_domain.api.v1.types import ProfileInput, OkType, MergeOutput, ProfileCreateOutput, \
    ProfileUpdateOutput
from person_domain.api.utils import get_search_person
from data_domain.managers import SampleManager, SampleObjectsName
from data_domain.matcher.main import MatcherAPI
from data_domain.models import BlobMeta

import django
import strawberry
from strawberry import ID
from strawberry.types import Info
from django.db.transaction import atomic
from django.conf import settings

from platform_lib.exceptions import BadInputDataException, InvalidJsonRequest
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import profile_info_scheme
from platform_lib.types import CustomBinaryType
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from platform_lib.utils import estimate_quality, get_workspace_id

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_persons(self, info: Info, person_ids: List[Optional[ID]]) -> OkType:
        ws_id = get_workspace_id(info)
        PersonManager.delete_persons(workspace_id=ws_id, person_ids=person_ids)

        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def merge_persons(self, info: Info, source_person_id: Optional[ID], target_person_id: Optional[ID],
                      activities_ids: List[Optional[ID]] = None) -> MergeOutput:
        with atomic():
            target_person = PersonManager.merge_persons(source_person_id=source_person_id,
                                                        activities_ids=activities_ids,
                                                        target_person_id=target_person_id)

            return MergeOutput(ok=True, target_person=target_person)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def add_profiles_to_groups(self, info: Info, group_ids: Optional[List[Optional[ID]]],
                               profiles_ids: Optional[List[Optional[ID]]]) -> OkType:
        ws_id = get_workspace_id(info)
        for profile_id in profiles_ids:
            manager = ProfileManager(workspace_id=ws_id, profile_id=profile_id)
            manager.add_labels(group_ids)
        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def remove_profiles_from_groups(self, info: Info, group_ids: Optional[List[Optional[ID]]],
                                    profiles_ids: Optional[List[Optional[ID]]]) -> OkType:
        ws_id = get_workspace_id(info)
        for profile_id in profiles_ids:
            manager = ProfileManager(workspace_id=ws_id, profile_id=profile_id)
            manager.remove_labels(group_ids)
        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def create_profile(self, info: Info, image: CustomBinaryType,
                       profile_data: Optional[ProfileInput] = None) -> ProfileCreateOutput:
        if profile_data is None:
            profile_data = ProfileInput()

        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        profile_data.info = profile_data.info or {}

        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get(
            'template_version',
            settings.DEFAULT_TEMPLATES_VERSION
        )

        objects_key = f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'

        processing_result = SampleManager.process_image(image=image, template_version=template_version)
        raw_template = processing_result[objects_key][0]['templates'][f"${template_version}"]

        processing_result_with_ids = SampleManager.create_blobs(workspace_id, meta=processing_result)
        face_meta_with_ids = processing_result_with_ids[objects_key][0]

        with atomic():
            sample = SampleManager.create_sample(workspace_id=workspace_id,
                                                 sample_meta={'$image': processing_result_with_ids['$image'],
                                                              objects_key: [face_meta_with_ids]})

            template_blob_meta_id = face_meta_with_ids['templates'][f'${template_version}']['id']

            template_blob_meta = BlobMeta.objects.select_for_update().get(id=template_blob_meta_id)
            template_blob_meta.meta.update({'sample_id': str(sample.id)})
            template_blob_meta.save()

        _, sample, quality = SampleManager.update_sample_quality(sample.id, template_version)

        search_list = MatcherAPI.search(workspace_id, template_version, [raw_template], 1)

        if not search_list:
            raise BadInputDataException('0xc3358b52')

        search_result = search_list[0]

        person = get_search_person(quality, search_result)
        if person:
            is_created = False
            profile = person.profile
            profile_data.info.update({'main_sample_id': str(sample.id)})

            profile_manager = ProfileManager(workspace_id, str(profile.id))

            profile_manager.add_labels(label_ids=profile_data.profile_group_ids)
            profile_manager.add_samples(sample_ids=[sample.id])
            profile_manager.update(info=profile_data.info)

            templates_info = [{'id': template_blob_meta_id, 'personId': str(profile.person_id)}]
            MatcherAPI.set_base_remove(workspace_id, template_version, [str(profile.person_id)])
            MatcherAPI.set_base_add(workspace_id, template_version, templates_info)
        else:
            is_created = True
            profile_data.info.update({
                'age': face_meta_with_ids.get('age'),
                'gender': face_meta_with_ids.get('gender').upper(),
                'main_sample_id': str(sample.id)
            })

            profile, _ = ProfileManager.create_with_person(workspace=workspace,
                                                           info=profile_data.info,
                                                           label_ids=profile_data.profile_group_ids,
                                                           sample_ids=[sample.id])

            templates_info = [{'id': template_blob_meta_id, 'personId': str(profile.person_id)}]
            MatcherAPI.set_base_add(workspace_id, template_version, templates_info)

        return ProfileCreateOutput(ok=True, profile=profile, is_created=is_created)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_profile(self, info: Info, profile_id: Optional[ID]) -> OkType:
        workspace_id = get_workspace_id(info=info)
        ProfileManager.delete(workspace_id, profile_id)
        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def update_profile(self, info: Info, profile_id: Optional[ID], profile_data: ProfileInput) -> ProfileUpdateOutput:
        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        workspace_id = get_workspace_id(info=info)

        profile = ProfileManager(workspace_id, profile_id).update(info=profile_data.info,
                                                                  label_ids=profile_data.profile_group_ids)
        return ProfileUpdateOutput(ok=True, profile=profile)
