import os
from typing import List

from django.apps import apps
from strawberry import ID

from notification_domain.managers import TriggerManager, EndpointManager, NotificationManager
from platform_lib.managers import TriggerMetaManager
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from platform_lib.types import JSONString, MutationResult
from platform_lib.utils import get_workspace_id

import django
import strawberry
from strawberry.types import Info

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


from user_domain.models import Workspace, Access  # noqa
from notification_domain.models import Endpoint, Trigger  # noqa
from notification_domain.api.v1.types import TriggerInput, TriggerManageOutput  # noqa


@strawberry.type
class Mutation:

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def create_trigger(self, info: Info, trigger_data: TriggerInput) -> TriggerManageOutput:
        workspace_id = get_workspace_id(info)

        label_model = apps.get_model('label_domain', 'Label')
        location = label_model.objects.get(workspace_id=workspace_id, id=trigger_data.location_id, type='LO')
        meta = TriggerMetaManager() \
            .add_location_overflow_variable([location], trigger_data.limit, ">") \
            .update_notification_params({'lifetime': trigger_data.lifetime}) \
            .get_meta()
        trigger_manager = TriggerManager(workspace_id=workspace_id)
        trigger = trigger_manager.create_trigger(title=trigger_data.title, meta=meta)
        return TriggerManageOutput(ok=True, trigger=trigger)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_trigger(self, info: Info, trigger_id: strawberry.ID) -> MutationResult:
        workspace_id = get_workspace_id(info)
        manager = TriggerManager(workspace_id=workspace_id)
        manager.delete_trigger(trigger_id=trigger_id)
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_endpoint(self, info: Info, ids: List[ID]) -> MutationResult:
        workspace_id = get_workspace_id(info)
        manager = EndpointManager(workspace_id=workspace_id)
        manager.delete_endpoint(endpoint_ids=ids)
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def viewing_notifications(self, info: Info, notification_ids: List[str]) -> MutationResult:
        workspace_id = get_workspace_id(info)
        manager = NotificationManager(workspace_id=workspace_id)
        manager.view(notification_ids=notification_ids)
        return MutationResult(ok=True)
