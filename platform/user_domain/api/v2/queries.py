import os
import django
import strawberry

from typing import List, Optional

from strawberry.types import Info

from platform_lib.strawberry_auth.permissions import CombinedPermission, IsAccessToken, IsAuthenticated, \
    IsServiceToken, IsHaveAccess
from platform_lib.utils import get_user, ApiError, type_desc, get_workspace_id
from user_domain.api.v2.types import AnalyticsOutput, WorkspaceType, AccessOutput, UserType
from user_domain.models import Workspace, Access

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from django.contrib.auth.models import AnonymousUser  # noqa


@strawberry.type
class InternalQuery:
    @strawberry.field(description="List of accesses")
    def accesses(self, info,
                 workspaces_ids: type_desc(Optional[List[strawberry.ID]],
                                           "Accesses workspace ids")) -> List[AccessOutput]:
        user = get_user(info)
        if isinstance(user, AnonymousUser):
            raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)
        if workspaces_ids:
            return Access.objects.filter(user=user, workspace__id__in=workspaces_ids)
        else:
            return Access.objects.filter(user=user)

    @strawberry.field(description="List of workspaces")
    def workspaces(self, info: Info) -> List[WorkspaceType]:
        accesses = Access.objects.filter(user=get_user(info))
        return Workspace.objects.filter(accesses__in=accesses)

    # TODO Remove when cognitive change api url
    @strawberry.field(permission_classes=[IsServiceToken])
    def workspace(self, info, workspace_id: Optional[str] = "") -> WorkspaceType:
        if workspace_id:
            return Workspace.objects.get(id=workspace_id)


@strawberry.type
class Query:

    @strawberry.field(permission_classes=[IsHaveAccess], description="Get links to analytics")
    def analytics(self, info) -> AnalyticsOutput:
        workspace_id = get_workspace_id(info)

        workspace = Workspace.objects.get(id=workspace_id)
        features = workspace.config.get('features', {})
        retail = features.get('retail_analytics', {}).get('url')
        advertising = features.get('advertising_analytics', {}).get('url')
        if not features:
            retail = workspace.config.get('url_elk')

        return AnalyticsOutput(
            retail=retail,
            advertising=advertising
        )

    @strawberry.field(
        permission_classes=[CombinedPermission(
            permissions=[IsAccessToken, IsAuthenticated],
            message='User is not authenticated or does not have an access token'
        )],
        description="Get information about user"
    )
    def me(self, info: Info) -> UserType:
        return get_user(info)  # noqa
