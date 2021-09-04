import json
import os
from typing import Optional

import django
import requests
import strawberry
from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Q
from django.db.transaction import atomic
from strawberry.types import Info

from licensing.common_managers import LicensingCommonEvent
from platform_lib.strawberry_auth.permissions import IsAuthenticated, IsServiceToken
from notification_domain.managers import EndpointManager
from platform_lib.types import JSONString
from platform_lib.utils import get_user, ApiError
from user_domain.api.v1.types import LoginSuccess, UserType, RegistrationInput, LogoutSuccess, \
    WorkspaceCreateOutput, WorkspaceConfigInput, WorkspaceConfigSetOutput, ElkOutput
from user_domain.managers import LoginManager, WorkspaceManager, AccessManager

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from django.contrib.auth.models import User, Group, AnonymousUser  # noqa
from user_domain.models import Workspace, Access  # noqa


@strawberry.type
class InternalMutation:
    @strawberry.field
    def login(self, info: Info, login: str, password: Optional[str] = None, confirmation_token: Optional[str] = None,
              workspace_id: Optional[str] = None) -> LoginSuccess:

        user = LoginManager.auth(login, password, info.context.request, confirmation_token, workspace_id)

        if user is None:
            raise Exception("Authorization error")

        return LoginSuccess(ok=True, workspaces=[a.workspace for a in user.accesses.all()])

    @strawberry.field
    def logout(self, info: Info) -> LogoutSuccess:
        auth_logout(request=info.context.request)
        return LogoutSuccess(ok=True)

    @strawberry.mutation
    def registration(self, user_info: RegistrationInput) -> UserType:
        with atomic():
            validate_password(password=user_info.user_password)
            if User.objects.filter(username=user_info.user_email).exists():
                raise Exception('User with this email already exists')
            if user_info.user_password == user_info.confirm_password:
                user = User.objects.create_user(username=user_info.user_email, email=user_info.user_email,
                                                password=user_info.user_password)
                user.first_name = user_info.user_name
                user.last_name = user_info.user_last_name
                user.save()

                locked_user = User.objects.select_for_update().get(id=user.id)
                workspace = WorkspaceManager.create_workspace(title="Workspace #1")
                EndpointManager(workspace_id=workspace.id).create_default_endpoints(owner_email=user.email)
                # LabelManager.create_default_labels(workspace_id=str(workspace.id))
                # TriggerManager.create_default_triggers(str(workspace.id))
                AccessManager.create_access(user=locked_user, workspace=workspace, permissions=Access.ADMIN)
            else:
                raise Exception("Wrong Password")
            return locked_user

    @strawberry.mutation(permission_classes=[IsServiceToken])
    def create_workspace(root, info: Info,
                         title: Optional[str] = "",
                         user_email: Optional[str] = "",
                         password: Optional[str] = "",
                         config: Optional[JSONString] = None) -> WorkspaceCreateOutput:

        if user_email:
            try:
                user = User.objects.get(Q(username__iexact=user_email) | Q(email__iexact=user_email))
            except User.DoesNotExist:
                user = User.objects.create(username=user_email, password='', email=user_email)
                if password == '':
                    user.set_unusable_password()
                else:
                    user.set_password(password)
                if user_email == settings.DEFAULT_QA_USER:
                    qa_group = Group.objects.get_or_create(name=settings.QA_GROUP)
                    user.groups.add(qa_group[0])
                user.save()
        else:
            user = get_user(info)
        if isinstance(user, AnonymousUser):
            raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)

        if config:
            config['template_version'] = settings.DEFAULT_TEMPLATES_VERSION
            config['features'] = {
                'retail_analytics': {
                    'enabled': True,
                }
            }

        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(id=user.id)
            standalone = user.groups.filter(name=settings.STANDALONE_GROUP).exists()
            workspace = WorkspaceManager.create_workspace(title=title, config=config)
            if standalone:
                LicensingCommonEvent(str(workspace.id)).create_workspace(user.username)
            locked_workspace = Workspace.objects.select_for_update().get(id=workspace.id)
            AccessManager.create_access(user=locked_user, workspace=locked_workspace, permissions=Access.ADMIN)

            if WorkspaceManager.is_retail(workspace):
                EndpointManager(workspace_id=workspace.id).create_default_endpoints(owner_email=user.email)
                # LabelManager.create_default_labels(str(workspace.id))
                # TriggerManager.create_default_triggers(str(workspace.id))

        return WorkspaceCreateOutput(workspace=locked_workspace, ok=True)

    @strawberry.mutation(permission_classes=[IsServiceToken])
    def set_workspace_config(root, info: Info,
                             workspace_id: strawberry.ID,
                             workspace_config: Optional[WorkspaceConfigInput] = None,
                             workspace_config_json: Optional[JSONString] = None) -> WorkspaceConfigSetOutput:

        if workspace_config is None and workspace_config_json is None:
            raise Exception('Undefined config.')

        with transaction.atomic():
            applied_config = workspace_config.to_dict() if workspace_config is not None else workspace_config_json

            workspace = WorkspaceManager.get_workspace(workspace_id)
            WorkspaceManager.update_workspace_config(workspace, applied_config)

        return WorkspaceConfigSetOutput(ok=True, config=workspace_config, config_json=workspace_config_json)

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def change_kibana_password(self, info: Info, password: Optional[str] = '') -> ElkOutput:
        if len(password) < 6:
            raise Exception('The password must be at least 6 characters long!')
        user = get_user(info=info)
        data = {'password': password}
        url_post = f'{settings.ELASTIC_URL_EXT}/_security/user/{user.username}/_password'
        response = requests.post(url_post, headers=settings.ELASTIC_HEADERS_EXT, data=json.dumps(data))
        if response.json().get('error'):
            raise Exception(response.json()["error"]["reason"])

        with atomic():
            for locked_ws in Workspace.objects.select_for_update().filter(accesses__user=user):
                if not locked_ws.config.get('kibana_password', False) and locked_ws.config.get('url_elk', False):
                    locked_ws.config.update({'kibana_password': password})
                    locked_ws.save()

        return ElkOutput(ok=True)


if not settings.ENABLE_ELK:
    delattr(InternalMutation, 'change_kibana_password')
