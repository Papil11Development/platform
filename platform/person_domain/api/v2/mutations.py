import os
from typing import List, Optional, Tuple

from person_domain.utils import ProfileMutationEventManager
from user_domain.managers import WorkspaceManager
from user_domain.models import Workspace  # noqa
from person_domain.managers import ProfileManager
from person_domain.models import Person, Profile  # noqa
from person_domain.api.v2.types import ProfileInput, ProfileCreateOutput, ProfileUpdateOutput, \
    ProfilesUpdateOutput
from person_domain.api.utils import get_search_person, handle_image, create_profile_info
from data_domain.managers import SampleManager, ActivityManager
from data_domain.matcher.main import MatcherAPI
from data_domain.models import Sample

import django
import strawberry
from strawberry import ID
from strawberry.types import Info
from django.db.transaction import atomic
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from platform_lib.exceptions import InvalidJsonRequest, BadInputDataException
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import profile_info_scheme
from platform_lib.utils import get_workspace_id, type_desc, validate_image
from platform_lib.types import CustomBinaryType, MutationResult
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from collector_domain.managers import AgentIndexEventManager


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Delete profiles by ids")
    def delete_profiles(root, info: Info,
                        profile_ids: type_desc(List[ID], "Profile ids to delete")) -> MutationResult:
        workspace_id = get_workspace_id(info=info)
        with atomic():
            for p_id in profile_ids:
                profile_m = ProfileManager(workspace_id, p_id)
                pmem = ProfileMutationEventManager(profile_m.profile)
                pmem.delete_profile()

            ProfileManager.delete_profiles(workspace_id, profile_ids)
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Update profile information")
    def update_profile(self, info: Info, profile_id: Optional[ID], profile_data: ProfileInput) -> ProfileUpdateOutput:
        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        workspace_id = get_workspace_id(info=info)
        profile_m = ProfileManager(workspace_id, profile_id)
        with atomic():
            pmem = ProfileMutationEventManager(profile_m.profile)
            pmem.update_profile(profile_data.profile_group_ids)
            profile = profile_m.update(profile_data.info, profile_data.profile_group_ids)
        return ProfileUpdateOutput(ok=True, profile=profile)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Add groups to profiles")
    def add_profiles_to_groups(self, info: Info,
                               group_ids: type_desc(List[ID], "List of group ids"),
                               profiles_ids: type_desc(List[ID], "List of profile ids")) -> ProfilesUpdateOutput:
        ws_id = get_workspace_id(info)
        profile_list = []
        with atomic():
            for profile_id in profiles_ids:
                profile_m = ProfileManager(workspace_id=ws_id, profile_id=profile_id)
                pmem = ProfileMutationEventManager(profile_m.profile)
                profile_m.add_labels(group_ids)
                pmem.update_profile(list(set(list(group_ids) + list(profile_m.current_groups_ids))))
                profile_list.append(profile_m.get_profile())

        return ProfilesUpdateOutput(ok=True,
                                    profiles=profile_list)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Remove groups from profiles")
    def remove_profiles_from_groups(self, info: Info,
                                    group_ids: type_desc(List[ID], "List of group ids"),
                                    profiles_ids: type_desc(List[ID],
                                                            "List of profile ids")) -> ProfilesUpdateOutput:
        ws_id = get_workspace_id(info)
        profile_list = []
        with atomic():
            for profile_id in profiles_ids:
                profile_m = ProfileManager(workspace_id=ws_id, profile_id=profile_id)

                pmem = ProfileMutationEventManager(profile_m.profile)  # warning
                profile_m.remove_labels(group_ids)
                if profile_m.profile.profile_groups.count():
                    pmem.update_profile(group_ids)
                else:
                    pmem.delete_profile()

                profile_list.append(profile_m.get_profile())

        return ProfilesUpdateOutput(ok=True,
                                    profiles=profile_list)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Create profile by photo or profile info")
    def create_profile(self, info: Info,
                       image: type_desc(Optional[CustomBinaryType],
                                        "Image for profile creation") = None,
                       profile_data: type_desc(Optional[ProfileInput],
                                               "Data for profile creation") = None) -> ProfileCreateOutput:

        if profile_data is None:
            profile_data = ProfileInput()
        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        profile_data.info = profile_data.info or {}

        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get('template_version', settings.DEFAULT_TEMPLATES_VERSION)

        if image is not None:
            validate_image(image)
            sample, _ = handle_image(image, template_version, workspace_id)
            blob_meta = SampleManager.get_face_crop_id(sample.meta)

            profile, person = create_profile_info(profile_data, workspace, sample, blob_meta)
            template_id = SampleManager.get_template_id(sample.meta, template_version)
            MatcherAPI.set_base_add(
                workspace_id, template_version, [{'id': template_id, 'personId': str(person.id)}]
            )
        else:
            profile, person = create_profile_info(profile_data, workspace)

        pmem = ProfileMutationEventManager(profile)
        pmem.add_profile(profile_data.profile_group_ids)

        return ProfileCreateOutput(ok=True, profile=profile, is_created=True)

    # NOT USED
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Create profile by photo or profile info with the search for an existing profile")
    def create_profile_with_search(self,
                                   info: Info,
                                   image: type_desc(Optional[CustomBinaryType], "Image for profile creation") = None,
                                   profile_data: type_desc(Optional[ProfileInput], "Data for profile creation") = None,
                                   search_similar: bool = False,
                                   ) -> ProfileCreateOutput:

        def update_existing_profile(ws_id: str, profile_id: str, data: ProfileInput, sample_id: str, blob_meta_id: str):
            profile_manager = ProfileManager(ws_id, profile_id)
            profile_manager.add_labels(label_ids=data.profile_group_ids)
            profile_manager.add_samples(sample_ids=[sample_id])
            profile_manager.update(info={**data.info, 'main_sample_id': sample_id, 'avatar_id': blob_meta_id})

        if profile_data is None:
            profile_data = ProfileInput()
        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        profile_data.info = profile_data.info or {}

        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get('template_version', settings.DEFAULT_TEMPLATES_VERSION)

        is_created = False

        with atomic():
            if image is not None:
                validate_image(image)
                sample, quality = handle_image(image, template_version, workspace_id)

                if search_similar:
                    raw_template = SampleManager.get_raw_template(sample.meta, template_version)

                    search_list = MatcherAPI.search(workspace_id, template_version, [raw_template], 1)
                    if not search_list:
                        raise BadInputDataException('0xc3358b52')

                    search_r = search_list[0]
                    person = get_search_person(quality, search_r)
                else:
                    person = None

                blob_meta = SampleManager.get_face_crop_id(sample.meta)

                template_id = SampleManager.get_template_id(sample.meta, template_version)
                if person:
                    profile = person.profile
                    update_existing_profile(workspace_id, str(profile.id), profile_data, str(sample.id), blob_meta)
                    MatcherAPI.set_base_remove(workspace_id, template_version, [str(person.id)])
                    MatcherAPI.set_base_add(workspace_id, template_version,
                                            [{'id': template_id, 'personId': str(person.id)}])
                else:
                    is_created = True
                    profile, person = create_profile_info(profile_data, workspace, sample, blob_meta)
                    MatcherAPI.set_base_add(workspace_id, template_version,
                                            [{'id': template_id, 'personId': str(person.id)}])
            else:
                is_created = True
                profile, person = create_profile_info(profile_data, workspace)

        person.refresh_from_db()
        return ProfileCreateOutput(ok=True, profile=profile, is_created=is_created)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Create profile by activity_id with profile info")
    def create_profile_by_activity(self, info: Info,
                                   activity_id: type_desc(ID, "Activity id for profile creation"),
                                   profile_data: type_desc(Optional[ProfileInput],
                                                           "Data for profile creation") = None) -> ProfileCreateOutput:
        if profile_data is None:
            profile_data = ProfileInput()
        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        profile_data.info = profile_data.info or {}

        workspace_id = get_workspace_id(info=info)
        workspace = WorkspaceManager.get_workspace(workspace_id)
        template_version = WorkspaceManager.get_template_version(workspace_id) or settings.DEFAULT_TEMPLATES_VERSION

        source_activity = ActivityManager.get_activity(workspace_id, activity_id)
        try:
            sample_id = ActivityManager.get_sample_id(source_activity)
            sample = SampleManager.get_sample(workspace_id, sample_id)
        except ObjectDoesNotExist:
            raise BadInputDataException('0x358vri3s')

        crop_image = SampleManager.get_face_crop_id(sample.meta)
        if not crop_image:
            raise BadInputDataException('0x358vri3s')

        person_id = ActivityManager.get_parent_process(source_activity).get('object', {}).get('id')
        with atomic():
            if person := (source_activity.person or Person.objects.filter(id=person_id).first()):
                if hasattr(person, 'profile') or settings.ENABLE_PROFILE_AUTOGENERATION:
                    is_created = False if person.profile.info.get('avatar_id') else True
                    profile_manager = ProfileManager(workspace_id, str(person.profile.id))
                    profile_manager.add_labels(label_ids=profile_data.profile_group_ids)
                    profile = profile_manager.update(info={'avatar_id': crop_image, **profile_data.info})
                else:
                    is_created = False
                    profile = ProfileManager.create(
                        workspace=workspace,
                        person=person,
                        info={'avatar_id': crop_image, **person.info, **profile_data.info},
                        label_ids=profile_data.profile_group_ids
                    )
            else:
                is_created = True
                profile_info = {'age': SampleManager.get_age(sample.meta),
                                'gender': SampleManager.get_gender(sample.meta),
                                'main_sample_id': sample_id,
                                'avatar_id': crop_image,
                                **profile_data.info}

                template_id = SampleManager.get_template_id(sample.meta, template_version)

                profile, person = ProfileManager.create_with_person(workspace=workspace,
                                                                    info=profile_info,
                                                                    label_ids=profile_data.profile_group_ids,
                                                                    sample_ids=[sample_id],
                                                                    person_id=person_id)

                MatcherAPI.set_base_add(workspace_id, template_version,
                                        [{'id': template_id, 'personId': person_id}])

            if not source_activity.person:
                with atomic():
                    locked_activity = ActivityManager.lock_activity(activity=source_activity)
                    locked_activity.person = person
                    locked_activity.save()

            pmem = ProfileMutationEventManager(profile)
            pmem.add_profile(profile_data.profile_group_ids)

        return ProfileCreateOutput(ok=True, profile=profile, is_created=is_created)
