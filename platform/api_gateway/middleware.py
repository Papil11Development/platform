from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError

from platform_lib.utils import database_sync_to_async
from user_domain.models import Workspace


class WorkspaceAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        workspace_id = scope['cookies'].get('workspace')
        user = scope['user']
        if not isinstance(user, AnonymousUser):
            try:
                await database_sync_to_async(lambda: Workspace.objects.get(id=workspace_id,
                                                                           accesses__user=user,
                                                                           config__is_active=True))()
            except (Workspace.DoesNotExist, ValidationError):
                scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)
