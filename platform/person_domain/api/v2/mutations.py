import os
from typing import List, Optional, Tuple

from person_domain.utils import ProfileMutationEventManager
from user_domain.managers import WorkspaceManager
from user_domain.models import Workspace  # noqa
from person_domain.managers import ProfileManager
from person_domain.models import Person, Profile, ProfileSettings  # noqa
from person_domain.api.v2.types import ProfileInput, ProfileCreateOutput, ProfileUpdateOutput, ProfilesUpdateOutput
from person_domain.api.utils import get_search_person, handle_image, create_profile_info
from data_domain.managers import SampleManager, ActivityManager
from data_domain.matcher.main import MatcherAPI

import django
import strawberry
from strawberry import ID
from strawberry.types import Info
from django.db.transaction import atomic
from django.db.models import F, Func, Value, JSONField
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from platform_lib.exceptions import InvalidJsonRequest, BadInputDataException
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import profile_info_scheme
from platform_lib.utils import get_workspace_id, type_desc, validate_image
from platform_lib.types import CustomBinaryType, MutationResult, ModifyExtraField, FieldsModifyResult
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Delete profiles by ids")
    def delete_profiles(root, info: Info,
                        profile_ids: type_desc(List[ID], "Profile ids to delete")) -> MutationResult:
        workspace_id = get_workspace_id(info=info)
        with atomic():
            for p_id in set(profile_ids):
                profile_m = ProfileManager(workspace_id, p_id)
                pmem = ProfileMutationEventManager(profile_m.profile)
                pmem.delete_profile()

            ProfileManager.delete_profiles(workspace_id, profile_ids)
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Update profile information")
    def update_profile(self, info: Info, profile_id: Optional[ID], profile_data: ProfileInput) -> ProfileUpdateOutput:
        if profile_data.info is not None and profile_data.fields is not None:
            raise Exception("Only one of the parameters info or fields is required")

        workspace_id = get_workspace_id(info=info)
        profile_data.info = profile_data.info or {}

        profile_m = ProfileManager(workspace_id, profile_id)
        pmem = ProfileMutationEventManager(profile_m.get_profile())
        main_sample_exists = profile_m.profile.info.get('main_sample_id') is not None
        is_update_avatar = profile_data.info and profile_data.info.get('avatar_id') is not None

        with atomic():
            p_settings, created = ProfileSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                p_settings.extra_fields = settings.REQUIRED_PROFILE_FIELDS
                p_settings.save()

        if profile_data.fields:
            profile_data.info = {item.name.lower(): item.value or None for item in profile_data.fields}

        missed_fields = set(profile_data.info) - set(p_settings.extra_fields)
        if missed_fields:
            raise Exception("One or more profile fields are unavailable")

        if not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        with atomic():
            profile = profile_m.update(profile_data.info, profile_data.profile_group_ids)
            if is_update_avatar and not main_sample_exists:
                pmem.add_profile(list(map(str, profile.profile_groups.values_list('id', flat=True))))
            elif main_sample_exists or is_update_avatar:
                pmem.update_profile(list(map(str, profile.profile_groups.values_list('id', flat=True))))
        return ProfileUpdateOutput(ok=True, profile=profile)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Add groups to profiles")
    def add_profiles_to_groups(self, info: Info,
                               group_ids: type_desc(List[ID], "List of group ids"),
                               profiles_ids: type_desc(List[ID], "List of profile ids")) -> ProfilesUpdateOutput:
        ws_id = get_workspace_id(info)
        profile_list = []
        with atomic():
            for profile_id in set(profiles_ids):
                profile_m = ProfileManager(workspace_id=ws_id, profile_id=profile_id)
                pmem = ProfileMutationEventManager(profile_m.profile)
                profile_m.add_labels(group_ids)
                if profile_m.profile.info.get('main_sample_id') is not None:
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
            for profile_id in set(profiles_ids):
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
        if profile_data.info is not None and profile_data.fields is not None:
            raise Exception("Only one of the parameters info or fields is required")

        profile_data.info = profile_data.info or {}

        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get('template_version', settings.DEFAULT_TEMPLATES_VERSION)

        with atomic():
            p_settings, created = ProfileSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                p_settings.extra_fields = settings.REQUIRED_PROFILE_FIELDS
                p_settings.save()
            available_fields = p_settings.extra_fields

        if profile_data.fields:
            profile_data.info = {item.name.lower(): item.value or None for item in profile_data.fields}

        missed_fields = set(profile_data.info) - set(available_fields)
        if missed_fields:
            raise Exception("One or more profile fields are unavailable")

        if not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        template_id = None
        if image is not None:
            validate_image(image)
            sample, _ = handle_image(image, template_version, workspace_id)

            profile, person = create_profile_info(profile_data, workspace, sample)
            template_id = SampleManager.get_template_id(sample.meta, template_version)
            MatcherAPI.set_base_add(
                workspace_id, template_version, [{'id': template_id, 'personId': str(person.id)}]
            )
        else:
            profile, person = create_profile_info(profile_data, workspace)

        pmem = ProfileMutationEventManager(profile)
        group_ids = profile_data.profile_group_ids if template_id else []
        pmem.add_profile(group_ids)

        return ProfileCreateOutput(ok=True, profile=profile, is_created=True)

    # NOT USED
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Create profile by photo or profile info with the search for an existing profile",
                         deprecation_reason="The mutation is not supported."
                                            " Use \"search\" and \"createProfile\" instead.")
    def create_profile_with_search(self,
                                   info: Info,
                                   image: type_desc(Optional[CustomBinaryType], "Image for profile creation") = None,
                                   profile_data: type_desc(Optional[ProfileInput], "Data for profile creation") = None,
                                   search_similar: bool = False,
                                   ) -> ProfileCreateOutput:

        def update_existing_profile(ws_id: str, profile_id: str, data: ProfileInput, sample_id: str):
            profile_manager = ProfileManager(ws_id, profile_id)
            profile_manager.add_labels(label_ids=data.profile_group_ids)
            profile_manager.add_samples(sample_ids=[sample_id])
            profile_manager.update(info={**data.info, 'main_sample_id': sample_id, 'avatar_id': sample_id})

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

                template_id = SampleManager.get_template_id(sample.meta, template_version)
                if person:
                    profile = person.profile
                    update_existing_profile(workspace_id, str(profile.id), profile_data, str(sample.id))
                    MatcherAPI.set_base_remove(workspace_id, template_version, [str(person.id)])
                    MatcherAPI.set_base_add(workspace_id, template_version,
                                            [{'id': template_id, 'personId': str(person.id)}])
                else:
                    is_created = True
                    profile, person = create_profile_info(profile_data, workspace, sample)
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
        if profile_data.info is not None and profile_data.fields is not None:
            raise Exception("Only one of the parameters info or fields is required")

        workspace_id = get_workspace_id(info=info)
        profile_data.info = profile_data.info or {}

        with atomic():
            p_settings, created = ProfileSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                p_settings.extra_fields = settings.REQUIRED_PROFILE_FIELDS
                p_settings.save()
            available_fields = p_settings.extra_fields

        if profile_data.fields:
            profile_data.info = {item.name.lower(): item.value or None for item in profile_data.fields}

        missed_fields = set(profile_data.info) - set(available_fields)
        if missed_fields:
            raise Exception("One or more profile fields are unavailable")

        if not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        if not workspace_id:
            raise BadInputDataException('0x500c29fa')

        workspace = WorkspaceManager.get_workspace(workspace_id)
        template_version = WorkspaceManager.get_template_version(workspace_id) or settings.DEFAULT_TEMPLATES_VERSION

        source_activity = ActivityManager.get_activity(workspace_id, activity_id)
        try:
            sample_id = ActivityManager.get_sample_id(source_activity)
            sample = SampleManager.get_sample(workspace_id, sample_id)
        except ObjectDoesNotExist:
            raise BadInputDataException('0x358vri3s')

        if not sample.meta:
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
                    profile = profile_manager.update(info={**profile_data.info, 'avatar_id': sample_id})
                else:
                    is_created = False
                    profile = ProfileManager.create(
                        workspace=workspace,
                        person=person,
                        info={**person.info, **profile_data.info, 'avatar_id': sample_id},
                        label_ids=profile_data.profile_group_ids,
                        sample_ids=[sample_id]
                    )
            else:
                is_created = True
                profile_info = {
                    'age': SampleManager.get_age(sample.meta),
                    'gender': SampleManager.get_gender(sample.meta)
                }
                profile_info.update({**profile_data.info, **{'main_sample_id': sample_id, 'avatar_id': sample_id}})

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

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def add_profiles_field(self, info: Info, field_input: ModifyExtraField) -> FieldsModifyResult:
        workspace_id = get_workspace_id(info=info)

        with atomic():
            p_settings, created = ProfileSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                fields = settings.REQUIRED_PROFILE_FIELDS
            else:
                fields = p_settings.extra_fields

            new_field = field_input.name.lower()
            if not new_field:
                return Exception("Profile field are unavailable")
            elif new_field in fields:
                return Exception("Profile field already exists")

            fields = fields + [new_field]
            p_settings.extra_fields = fields
            p_settings.save()

        return FieldsModifyResult(ok=True, fields=fields)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def remove_profiles_field(self, info: Info, field_input: ModifyExtraField) -> FieldsModifyResult:
        workspace_id = get_workspace_id(info=info)

        with atomic():
            p_settings, created = ProfileSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                fields = settings.REQUIRED_PROFILE_FIELDS
            else:
                fields = p_settings.extra_fields

            new_field = field_input.name.lower()
            if new_field in settings.REQUIRED_PROFILE_FIELDS:
                return Exception("Profile field is required")

            if new_field not in fields:
                return Exception("Profile field does not exists")

            fields.remove(new_field)
            p_settings.extra_fields = fields

            Profile.objects.filter(workspace_id=workspace_id).update(
                info=Func(
                    F("info") - new_field,
                    function="jsonb"
                )
            )
            p_settings.save()

        return FieldsModifyResult(ok=True, fields=fields)
