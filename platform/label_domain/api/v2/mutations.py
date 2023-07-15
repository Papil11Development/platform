import os
import json
from typing import List

from strawberry import ID

from label_domain.managers import LabelManager
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from platform_lib.types import MutationResult
from platform_lib.utils import get_workspace_id, type_desc

import django
import strawberry
from strawberry.types import Info
from django.db.transaction import atomic

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from user_domain.models import Workspace, Access  # noqa
from label_domain.models import Label  # noqa
from label_domain.api.v2.types import ProfileGroupInput, ProfileGroupModifyOutput, ProfileGroupModifyInput  # noqa
from person_domain.utils import ProfileMutationEventManager  # noqa


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Create new profile group")
    def create_profile_group(self, info: Info,
                             profile_group_data: type_desc(ProfileGroupInput,
                                                           "Profile group data")) -> ProfileGroupModifyOutput:
        workspace_id = get_workspace_id(info)

        with atomic():
            manager = LabelManager(workspace_id=workspace_id)
            label = manager.create_label(profile_group_data.info,
                                         profile_group_data.title,
                                         label_type=str(Label.PROFILE_GROUP))

        return ProfileGroupModifyOutput(ok=True, profile_group=label)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Delete profile group")
    def delete_profile_group(self, info: Info,
                             group_ids: type_desc(List[ID], "Profile group ids to delete")) -> MutationResult:
        workspace_id = get_workspace_id(info)
        with atomic():
            for gr_id in set(group_ids):
                lm = LabelManager(workspace_id=workspace_id, label_id=gr_id)
                for pr in lm.label.profiles.all():
                    pr_gr_ids = list(map(str, pr.profile_groups.all().values_list('id', flat=True)))
                    pmem = ProfileMutationEventManager(pr)
                    pmem.update_profile(list(set(pr_gr_ids) - set(group_ids)))

            lm = LabelManager(workspace_id=workspace_id)
            lm.delete_labels(group_ids, LabelManager.Types.PROFILE_GROUP)

        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Update profile group info")
    def update_profile_group_info(self, info: Info,
                                  profile_group_id: type_desc(ID, "Updated profile group id"),
                                  profile_group_data: type_desc(ProfileGroupModifyInput,
                                                                "Data for update")) -> ProfileGroupModifyOutput:
        workspace_id = get_workspace_id(info)
        manager = LabelManager(workspace_id=workspace_id, label_id=profile_group_id)
        manager.change_label_info(info=profile_group_data.info, title=profile_group_data.title)
        return ProfileGroupModifyOutput(ok=True, profile_group=manager.get_label())
