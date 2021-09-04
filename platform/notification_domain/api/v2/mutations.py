import os
from typing import List, Optional

from django.apps import apps
from django.db import transaction

from strawberry import ID

from notification_domain.api.v2.types import EndpointManageOutput, EmailEndpointInput, \
    WebhookEndpointInput, TriggerManageOutput, DefaultEndpointAlias
from notification_domain.managers import NotificationManager, TriggerManager, EndpointManager
from notification_domain.models import Endpoint
from platform_lib.exceptions import BadInputDataException
from platform_lib.utils import get_workspace_id, type_desc
from platform_lib.types import MutationResult, JSONString
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive

import django
import strawberry
from strawberry.types import Info

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


@strawberry.type
class Mutation:

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Set the is_viewed for notification")
    def viewing_notifications(self,
                              info: Info,
                              notification_ids: type_desc(List[str], "List of notification ids")) -> MutationResult:
        workspace_id = get_workspace_id(info)
        manager = NotificationManager(workspace_id=workspace_id)
        manager.view(notification_ids=notification_ids)
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Mark all notifications as viewed")
    def mark_all_notifications_as_viewed(self, info: Info) -> MutationResult:
        workspace_id = get_workspace_id(info)
        manager = NotificationManager(workspace_id=workspace_id)
        manager.view_all()
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Link endpoint to trigger")
    def link_endpoint(self, info: Info,
                      trigger_id: ID,
                      endpoint_alias: Optional[DefaultEndpointAlias] = None,
                      endpoint_id: Optional[ID] = None) -> MutationResult:
        with transaction.atomic():
            workspace_id = get_workspace_id(info)

            if endpoint_alias:
                endpoint = EndpointManager(workspace_id=workspace_id).get_default_by_alias([endpoint_alias])[0]
            elif endpoint_id:
                endpoint = EndpointManager(workspace_id=workspace_id, endpoint_id=endpoint_id).get_endpoint()
            else:
                raise BadInputDataException("No id or alias provided")

            TriggerManager.add_endpoint(trigger_id, endpoint)

            return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Unlink endpoint from trigger")
    def unlink_endpoint(self, info: Info,
                        trigger_id: ID,
                        endpoint_alias: Optional[DefaultEndpointAlias] = None,
                        endpoint_id: Optional[ID] = None) -> MutationResult:
        with transaction.atomic():
            workspace_id = get_workspace_id(info)

            if endpoint_alias:
                endpoint = EndpointManager(workspace_id=workspace_id).get_default_by_alias([endpoint_alias])[0]
            elif endpoint_id:
                endpoint = EndpointManager(workspace_id=workspace_id, endpoint_id=endpoint_id).get_endpoint()
            else:
                raise BadInputDataException("No id or alias provided")

            TriggerManager.remove_endpoint(trigger_id, endpoint)

            return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Create new email endpoint")
    def create_email_endpoint(self, info: Info, endpoint_data: EmailEndpointInput) -> EndpointManageOutput:
        workspace_id = get_workspace_id(info)
        manager = EndpointManager(workspace_id=workspace_id)
        endpoint = manager.create_email_endpoint(target_email=endpoint_data.target_email)

        return EndpointManageOutput(ok=True, endpoint=endpoint)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description="Create new webhook endpoint")
    def create_webhook_endpoint(self, info: Info, endpoint_data: WebhookEndpointInput) -> EndpointManageOutput:
        workspace_id = get_workspace_id(info)
        manager = EndpointManager(workspace_id=workspace_id)
        endpoint = manager.create_webhook_endpoint(url=endpoint_data.url, method=endpoint_data.request_method)

        return EndpointManageOutput(ok=True, endpoint=endpoint)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Update endpoint data")
    def update_endpoint(self, info: Info,
                        endpoint_id: ID,
                        endpoint_info: JSONString) -> EndpointManageOutput:
        with transaction.atomic():
            workspace_id = get_workspace_id(info)
            endpoint = Endpoint.objects.select_for_update().get(id=endpoint_id, workspace_id=workspace_id)
            endpoint.meta.update(endpoint_info)
            endpoint.save()

            return EndpointManageOutput(ok=True, endpoint=endpoint)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Delete endpoint")
    def delete_endpoint(self, info: Info, endpoint_ids: List[str]) -> MutationResult:
        workspace_id = get_workspace_id(info)
        manager = EndpointManager(workspace_id=workspace_id)
        manager.delete_endpoint(endpoint_ids=endpoint_ids)
        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                         description='Create new trigger for profile group witch will'
                                     'send events if people from group will be detected')
    def create_profile_group_trigger(
            self,
            info: Info,
            profile_group_id: ID,
            title: Optional[str] = None,
            endpoint_ids: Optional[List[ID]] = None,
            endpoint_aliases: Optional[List[DefaultEndpointAlias]] = None,
            endpoint_url: Optional[str] = None
    ) -> TriggerManageOutput:

        workspace_id = get_workspace_id(info)
        label_model = apps.get_model('label_domain', 'Label')
        trigger_manager = TriggerManager(workspace_id=workspace_id)
        profile_group = label_model.objects.get(workspace_id=workspace_id, id=profile_group_id, type='PG')

        endpoints = []
        endpoint_manager = EndpointManager(workspace_id=workspace_id)

        if endpoint_ids is not None:
            endpoints += endpoint_manager.get_by_ids(endpoint_ids)

        if endpoint_aliases is not None:
            endpoints += endpoint_manager.get_default_by_alias(endpoint_aliases)

        if endpoint_url is not None:
            endpoints += [endpoint_manager.create_webhook_endpoint(url=endpoint_url, method="POST")]

        trigger = trigger_manager.create_label_trigger(
            title=title,
            endpoints=endpoints,
            targets_list=[profile_group]
        )

        return TriggerManageOutput(ok=True, trigger=trigger)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def update_trigger(self, info: Info,
                       trigger_id: ID,
                       title: Optional[str] = None,
                       endpoint_ids: Optional[List[ID]] = None,
                       endpoint_aliases: Optional[List[DefaultEndpointAlias]] = None) -> TriggerManageOutput:
        workspace_id = get_workspace_id(info)
        trigger_manager = TriggerManager(workspace_id=workspace_id)

        endpoints = []

        if endpoint_ids is not None:
            endpoints += EndpointManager(workspace_id=workspace_id).get_by_ids(endpoint_ids)

        if endpoint_aliases is not None:
            endpoints += EndpointManager(workspace_id=workspace_id).get_default_by_alias(endpoint_aliases)

        updated_trigger = trigger_manager.update_trigger(
            trigger_id,
            title,
            endpoints if (endpoint_ids is not None or endpoint_aliases is not None) else None
        )

        return TriggerManageOutput(
            ok=True,
            trigger=updated_trigger
        )

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description='Delete trigger')
    def delete_trigger(self, info: Info, trigger_id: ID) -> MutationResult:
        workspace_id = get_workspace_id(info)
        trigger_manager = TriggerManager(workspace_id=workspace_id)
        trigger_manager.delete_trigger(trigger_id)
        return MutationResult(ok=True)
