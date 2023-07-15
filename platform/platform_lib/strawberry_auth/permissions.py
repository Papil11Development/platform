import uuid
from typing import List, Union, Optional, Any

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ObjectDoesNotExist
from strawberry.permission import BasePermission
from strawberry.types import Info

from api_gateway.api.token import Token
from licensing.models import License
from platform_lib.exceptions import InvalidToken
from platform_lib.utils import get_token, get_workspace_id, get_user, get_license_id, utcnow_with_tz
from user_domain.models import Workspace, Access
from licensing.common_managers import LicensingCommonEvent
from plib.tracing.utils import get_tracer, ContextStub


class CombinedPermission(BasePermission):
    """
    Permission class that allows you to apply the `or` operation to a group of BasePermission
    """

    permissions: List[BasePermission] = []

    def __call__(self):
        return self

    def __init__(self, permissions: List[BasePermission], message: Optional[str] = None):
        if not message:
            message = ' or '.join([p.message for p in permissions])
        self.message = message
        self.permissions = permissions

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_combined") if tracer else ContextStub() as span:
            span.set_attribute("permission_list", str(self.permissions))

            for permission in self.permissions:
                if permission.has_permission(self=self, source=source, info=info, **kwargs):
                    return True
            return False


class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_is_authenticated") if tracer else ContextStub() as span:
            user = get_user(info=info)

            return not isinstance(user, AnonymousUser)


class IsAgentToken(BasePermission):
    message = "Agent token is invalid"

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        token = get_token(info=info)

        try:
            token = Token.from_string(token)
        except InvalidToken:
            return False
        if token.is_agent():
            info.context.request.META['HTTP_TOKEN'] = token
        else:
            return False
        return True


class IsHaveAccess(BasePermission):
    message = "User has no access or id is incorrect"

    @staticmethod
    def __check_workspace_and_return_access(workspace_id: Union[str, uuid.UUID],
                                            user: User) -> Optional[Access]:
        if isinstance(user, AnonymousUser):
            user = None

        try:
            in_access = Access.objects.select_related('workspace').get(workspace_id=workspace_id)
        except Access.DoesNotExist:
            in_access = None

        if (user is not None) and (in_access is not None) and (in_access in user.accesses.all()):
            return in_access
        else:
            return None

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_is_have_access") if tracer else ContextStub() as span:
            token = get_token(info=info)
            workspace_id = get_workspace_id(info=info)
            user = get_user(info=info)
            workspace = None

            if token:

                try:
                    token = Token.from_string(token)
                except InvalidToken:
                    return False

                if token.is_access():
                    workspace = Workspace.objects.get(accesses__id=token.id)
                if token.is_activation():
                    workspace = Workspace.objects.get(agents__activations__id=token.id)
                if token.is_agent():
                    workspace = Workspace.objects.get(agents__id=token.id)

            elif workspace_id is not None:

                try:
                    workspace_id = uuid.UUID(workspace_id)
                except ValueError:
                    return False

                if (access := self.__check_workspace_and_return_access(workspace_id, user)) is not None:
                    token = access.id
                    workspace = access.workspace

            if workspace is not None and token is not None:
                info.context.request.META['workspace_id'] = str(workspace.id)
                info.context.request.META['HTTP_TOKEN'] = str(token)

                return True
            else:
                return False


class IsWorkspaceActive(BasePermission):
    message = "User workspace is inactive"

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        def get_license_status():
            try:
                is_active = LicensingCommonEvent(workspace_id).is_active()
                cache.setdefault(workspace_id, {}).update({'status': is_active, 'last_update': now})
                return is_active
            except NotImplementedError:
                cache.setdefault(workspace_id, {}).update({'status': False, 'last_update': now})
                return False

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_is_workspace_active") if tracer else ContextStub() as span:

            workspace_id = get_workspace_id(info=info)

            # TODO Delete after licensing fix
            if settings.IS_ON_PREMISE:
                cache = settings.GLOBAL_LICENSING_CACHE
                ws_cache = cache.get(workspace_id)
                now = utcnow_with_tz()

                last_update = ws_cache.get('last_update') if ws_cache else now

                if ws_cache is None or (now - last_update).total_seconds() > settings.VERIFY_LICENSE_DELTA:
                    return get_license_status()
                elif ws_cache and not ws_cache.get('status'):
                    return get_license_status()
                else:
                    return ws_cache.get('status')
            else:
                try:
                    workspace = Workspace.objects.get(id=workspace_id)
                except Workspace.DoesNotExist:
                    return False

                return bool(workspace.config.get('is_active'))


class IsServiceToken(BasePermission):
    message = "Wrong token or token is not provided"

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_is_service_token") if tracer else ContextStub() as span:
            try:
                token = Token.from_string(get_token(info=info))
            except InvalidToken:
                return False

            return token.is_service()


class IsAccessToken(BasePermission):
    message = "Wrong token or token is not provided"

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_is_access_token") if tracer else ContextStub() as span:
            try:
                token = Token.from_string(get_token(info=info))
            except InvalidToken:
                return False
            if token.is_access():
                info.context.request.user = Access.objects.get(id=token.id).user
                return True

            return False


class IsLicenseExists(BasePermission):
    message = "License does not exist"

    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("perm_is_license_exists") if tracer else ContextStub() as span:
            user = get_user(info)
            license_id = get_license_id(info)

            try:
                license_id = uuid.UUID(license_id) if license_id else None
            except ValueError:
                return False

            try:
                lic = License.objects.select_related('billing_account', 'workspace', 'product') \
                             .get(id=license_id, billing_account__user=user)
            except ObjectDoesNotExist:
                return False

            info.context.request.META['license'] = lic

            return True
