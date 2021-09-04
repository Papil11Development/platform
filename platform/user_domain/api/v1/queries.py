import os
from typing import List, Optional

import strawberry
from strawberry.types import Info

from platform_lib.strawberry_auth.permissions import IsServiceToken, IsHaveAccess
from platform_lib.utils import get_user, ApiError, get_workspace_id

from user_domain.models import Workspace, Access
from user_domain.api.v1.types import UserType, WorkspaceType, AccessOutput, AnalyticsOutput

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from django.contrib.auth.models import User, AnonymousUser  # noqa


@strawberry.type
class InternalQuery:

    @strawberry.field
    def resolve_users(root, info) -> List[UserType]:
        return User.objects.filter(id=get_user(info))

    @strawberry.field
    def accesses(self, info, workspaces_ids: Optional[List[strawberry.ID]]) -> List[AccessOutput]:
        user = get_user(info)
        if isinstance(user, AnonymousUser):
            raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)
        if workspaces_ids:
            return Access.objects.filter(user=user, workspace__id__in=workspaces_ids)
        else:
            return Access.objects.filter(user=user)

    @strawberry.field(permission_classes=[IsServiceToken])
    def workspace(self, info, workspace_id: Optional[str] = "") -> WorkspaceType:

        if workspace_id:
            return Workspace.objects.get(id=workspace_id)

    @strawberry.field
    def workspaces(self, info) -> List[WorkspaceType]:
        accesses = Access.objects.filter(user=get_user(info))
        return Workspace.objects.filter(accesses__in=accesses)


@strawberry.type
class Query:

    @strawberry.field(permission_classes=[IsHaveAccess], description="Get links to analytics")
    def analytics(self, info: Info) -> AnalyticsOutput:
        workspace_id = get_workspace_id(info)

        workspace = Workspace.objects.get(id=workspace_id)
        features = workspace.config.get('features', {})
        retail = features.get('retail_analytics', {}).get('url')
        advertising = features.get('advertising_analytics', {}).get('url')
        if not retail:
            retail = workspace.config.get('url_elk')

        return AnalyticsOutput(
            retail=retail,
            advertising=advertising
        )

    # TODO Remove stub resolver later
    @strawberry.field(permission_classes=[IsHaveAccess])
    def stub(self, info) -> str:
        return ''
