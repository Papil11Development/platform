import os
from typing import List, Optional

from strawberry import ID

from label_domain.managers import LabelManager
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from platform_lib.types import JSONString
from platform_lib.utils import get_workspace_id

import django
import strawberry
from strawberry.types import Info
from django.db.transaction import atomic

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from user_domain.models import Workspace, Access  # noqa
from label_domain.models import Label  # noqa
from label_domain.api.v1.types import LocationInput, LocationModifyOutput, OkType  # noqa


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def create_location(self, info: Info, location_data: LocationInput) -> LocationModifyOutput:
        workspace_id = get_workspace_id(info)
        with atomic():
            manager = LabelManager(workspace_id=workspace_id)
            label = manager.create_label(location_data.info,
                                         location_data.info.get("title", ""),
                                         label_type=str(Label.LOCATION))

        return LocationModifyOutput(ok=True, location=label)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_location(self, info: Info, location_id: Optional[ID]) -> OkType:
        workspace_id = get_workspace_id(info)
        with atomic():
            Label.objects.select_for_update().filter(workspace__id=workspace_id,
                                                     id=location_id, type=Label.LOCATION).delete()

        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def create_profile_group(self, info: Info, location_data: LocationInput) -> LocationModifyOutput:
        workspace_id = get_workspace_id(info)
        with atomic():
            location_data.title = location_data.info.get('title', '')

            manager = LabelManager(workspace_id=workspace_id)
            label = manager.create_label(location_data.info, location_data.title,
                                         label_type=str(Label.PROFILE_GROUP))

        return LocationModifyOutput(ok=True, location=label)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_profile_group(self, info: Info, ids: List[ID]) -> OkType:
        workspace_id = get_workspace_id(info)
        with atomic():
            Label.objects.select_for_update().filter(workspace__id=workspace_id,
                                                     id__in=ids, type=Label.PROFILE_GROUP).delete()

        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def create_area_type(self, info: Info, location_data: LocationInput) -> LocationModifyOutput:
        workspace_id = get_workspace_id(info)
        with atomic():
            location_data.title = location_data.info.get('title', '')

            manager = LabelManager(workspace_id=workspace_id)
            label = manager.create_label(location_data.info, location_data.title,
                                         label_type=str(Label.PROFILE_GROUP))

        return LocationModifyOutput(ok=True, location=label)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_area_type(self, info: Info, ids: List[Optional[ID]]) -> OkType:
        workspace_id = get_workspace_id(info)
        with atomic():
            Label.objects.select_for_update().filter(workspace__id=workspace_id,
                                                     id__in=ids, type=Label.AREA_TYPE).delete()

        return OkType(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def update_location_info(self, info: Info, location_id: ID, location_data: LocationInput) -> LocationModifyOutput:
        workspace_id = get_workspace_id(info)
        manager = LabelManager(workspace_id=workspace_id, label_id=location_id)
        manager.change_label_info(info=location_data.info, title=location_data.info.get('title'))
        return LocationModifyOutput(ok=True, location=manager.get_label())
