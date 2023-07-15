import os
from typing import Tuple

import django
import strawberry
from django.conf import settings
from django.db import transaction
from strawberry.types import Info
from strawberry import ID

from data_domain.managers import SampleManager
from data_domain.matcher import MatcherAPI
from data_domain.models import Sample

from person_domain.api.v2.types import ProfileInput, ProfileCreateOutput
from person_domain.models import Profile, Person
from person_domain.api.v2.mutations import Mutation as Mutation_v2
from person_domain.api.v2.types import ProfileUpdateOutput
from person_domain.managers import ProfileManager, PersonManager

from user_domain.models import Workspace

from platform_lib.exceptions import InvalidJsonRequest
from platform_lib.utils import get_workspace_id
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import profile_info_scheme
from platform_lib.types import MutationResult

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


@strawberry.type
class Mutation(Mutation_v2):
    @strawberry.mutation
    def delete_profile_sample(self, info: Info, profile_id: ID) -> ProfileUpdateOutput:
        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get(
            'template_version',
            settings.DEFAULT_TEMPLATES_VERSION
        )

        profile_m = ProfileManager(workspace_id, profile_id)
        person_m = PersonManager(workspace_id, str(profile_m.profile.person_id))
        if profile_m.profile.info.get('main_sample_id'):
            profile_m.delete_profile_main_sample()
            person_m.delete_person_main_sample()
            person_ids = [str(profile_m.profile.person_id)]

            MatcherAPI.set_base_remove(workspace_id, template_version, person_ids)
            group_ids = [str(label) for label in profile_m.profile.profile_groups.values_list('id', flat=True)]
            for group_id in group_ids:
                MatcherAPI.set_base_remove(group_id, template_version, person_ids)

        return ProfileUpdateOutput(ok=True, profile=profile_m.profile)

    @strawberry.mutation(description="Create profile by photo or profile info")
    def create_profile(self, info: Info, profile_data: ProfileInput) -> ProfileCreateOutput:

        def create_profile_info(data: ProfileInput, p_sample: Sample) -> Tuple[Profile, Person]:

            profile_info = data.info
            sample_ids = None
            if p_sample:
                profile_info.update({'age': SampleManager.get_age(p_sample.meta),
                                     'gender': SampleManager.get_gender(p_sample.meta).upper(),
                                     'main_sample_id': str(p_sample.id)})
                sample_ids = [str(p_sample.id)]

            created_profile, created_person = ProfileManager.create_with_person(workspace=workspace,
                                                                                info=profile_info,
                                                                                label_ids=data.profile_group_ids,
                                                                                sample_ids=sample_ids)

            return created_profile, created_person

        if profile_data.info and not is_valid_json(profile_data.info, profile_info_scheme):
            raise InvalidJsonRequest()

        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get(
            'template_version',
            settings.DEFAULT_TEMPLATES_VERSION
        )
        sample = None
        if sample_id := profile_data.info.get('main_sample_id'):
            sample_meta = SampleManager.get_sample(workspace_id, sample_id).meta
            template_id = SampleManager.get_template_id(sample_meta, template_version)

            sample = SampleManager.get_sample(workspace_id, sample_id)
        profile, person = create_profile_info(profile_data, sample)
        if sample:
            MatcherAPI.set_base_add(workspace_id, template_version,
                                    [{'id': template_id,
                                      'personId': str(profile.person.id)}])

        person.refresh_from_db()
        return ProfileCreateOutput(ok=True, profile=person.profile, is_created=True)

    @strawberry.mutation
    def update_main_sample(self,
                           info: Info,
                           profile_id: ID,
                           sample_id: ID) -> MutationResult:
        workspace_id = get_workspace_id(info)
        workspace = Workspace.objects.get(id=workspace_id)
        template_version = workspace.config.get(
            'template_version',
            settings.DEFAULT_TEMPLATES_VERSION
        )

        created = False

        from data_domain.managers import SampleManager

        with transaction.atomic():
            profile_manager = ProfileManager(workspace_id=workspace_id, profile_id=profile_id)
            profile = profile_manager.get_profile()

            person_id = str(profile.person_id)
            person_manager = PersonManager(workspace_id=workspace_id, person_id=person_id)

            source_sample = SampleManager.get_sample(workspace_id=workspace_id, sample_id=sample_id)

            try:
                main_sample = SampleManager.change_meta_to_new(workspace_id=workspace_id,
                                                               destination_sample_id=profile.info.get('main_sample_id'),
                                                               origin_sample_id=sample_id)
            except Sample.DoesNotExist:
                main_sample = SampleManager.create_sample(workspace_id=workspace_id, sample_meta=source_sample.meta)
                with transaction.atomic():
                    profile_manager.update(info={'main_sample_id': str(main_sample.id)},
                                           sample_ids=[str(main_sample.id)])
                    person_manager.update(info={'main_sample_id': str(main_sample.id)},
                                          sample_ids=[str(main_sample.id)])

                created = True

        template_info = [{
            'id': SampleManager.get_template_id(main_sample.meta, template_version),
            'personId': person_id
        }]
        if not created:
            MatcherAPI.set_base_remove(workspace_id, template_version, [person_id])
            MatcherAPI.set_base_add(workspace_id, template_version, template_info)
            for label in profile.profile_groups.all():
                MatcherAPI.set_base_remove(str(label.id), template_version, [person_id])
                MatcherAPI.set_base_add(str(label.id), template_version, template_info)
        else:
            MatcherAPI.set_base_add(workspace_id, template_version, template_info)
            for label in profile.profile_groups.all():
                MatcherAPI.set_base_add(str(label.id), template_version, template_info)

        return MutationResult(ok=True)
