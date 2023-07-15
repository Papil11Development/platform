import dataclasses
import os
import django
import strawberry

from typing import Optional
from django.db import transaction
from django.conf import settings
from django.db.models import Q
from django.contrib.auth import logout as auth_logout, update_session_auth_hash
from strawberry.types import Info

from licensing.common_managers import LicensingCommonEvent
from platform_lib.strawberry_auth.permissions import IsServiceToken, IsHaveAccess
from platform_lib.types import MutationResult, JSONString
from platform_lib.utils import type_desc, ApiError, get_user, get_workspace_id, delete_none_from_dict
from platform_lib.exceptions import InvalidJsonRequest
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import workspace_config_scheme

from user_domain.api.utils import change_kibana_password
from user_domain.api.v2.types import (RegistrationInput, ChangePasswordInput, RegistrationOutput, ResetPasswordInput,
                                      ConfirmationInput, LoginResult, WorkspaceCreateOutput, WorkspaceConfigInput,
                                      WorkspaceConfigSetOutput, WorkspaceConfigUpdateOutput, WorkspaceConfigUpdateInput)
from user_domain.managers import LoginManager, EmailManager, WorkspaceManager, AccessManager

from label_domain.managers import LabelManager

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from django.contrib.auth.models import User, Group, AnonymousUser  # noqa
from user_domain.models import Workspace, Access  # noqa


@strawberry.type
class InternalMutation:
    @strawberry.mutation(description="Login to account")
    def login(self, info: Info,
              login: type_desc(str, "user login"),
              password: type_desc(Optional[str], "User password")) -> LoginResult:

        user = LoginManager.auth(login, password, info.context.request)

        return LoginResult(ok=True, me=user)

    @strawberry.mutation(description="Logout from account")
    def logout(self, info: Info) -> MutationResult:
        auth_logout(request=info.context.request)
        return MutationResult(ok=True)

    @strawberry.mutation(description="Register an account")
    def registration(self, user_info: RegistrationInput) -> RegistrationOutput:
        user = LoginManager.registration(email=user_info.email,
                                         password=user_info.password,
                                         confirm_password=user_info.confirm_password,
                                         first_name=user_info.first_name,
                                         last_name=user_info.last_name)

        return RegistrationOutput(ok=True, user=user)

    @strawberry.mutation(description="Change user's password")
    def change_password(self, info: Info, user_info: ChangePasswordInput) -> MutationResult:
        with transaction.atomic():
            if info.context.request.user.is_authenticated:
                user = LoginManager.change_password(user_id=str(info.context.request.user.id),
                                                    old_password=user_info.old_password,
                                                    new_password=user_info.new_password,
                                                    confirm_new_password=user_info.confirm_new_password)
                change_kibana_password(username=user.email,
                                       password=user_info.new_password)
                update_session_auth_hash(info.context.request, user)
            else:
                raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)
            return MutationResult(ok=True)

    @strawberry.mutation(description="Send password reset email")
    def send_reset_password_email(self, info: Info, email: type_desc(str, "User email")) -> MutationResult:
        EmailManager.send_email(user=info.context.request.user,
                                email_key=EmailManager.RESET_PASSWORD,
                                email=email)
        return MutationResult(ok=True)

    @strawberry.mutation(description="Reset user's password")
    def reset_password(self, info: Info, user_info: ResetPasswordInput) -> MutationResult:
        with transaction.atomic():
            user = LoginManager.reset_password(user_id=user_info.user_id,
                                               confirmation_token=user_info.confirmation_token,
                                               new_password=user_info.new_password,
                                               confirm_new_password=user_info.confirm_new_password)
            change_kibana_password(username=user.email,
                                   password=user_info.new_password)
            return MutationResult(ok=True)

    @strawberry.mutation(description="Send confirm registration email")
    def send_confirmation_email(self, info: Info, email: type_desc(str, "User email")) -> MutationResult:
        EmailManager.send_email(user=info.context.request.user,
                                email_key=EmailManager.CONFIRM_EMAIL,
                                email=email)
        return MutationResult(ok=True)

    @strawberry.mutation(description="Confirm registration")
    def confirm(self, info: Info, user_info: ConfirmationInput) -> MutationResult:
        with transaction.atomic():
            LoginManager.confirm_registration(user_id=user_info.user_id,
                                              confirmation_token=user_info.confirmation_token)
            return MutationResult(ok=True)

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
            config.update({
                'template_version': settings.DEFAULT_TEMPLATES_VERSION,
                'features': {
                    'retail_analytics': {
                        'enabled': True,
                    }
                },
                'activity_score_threshold': settings.DEFAULT_SCORE_THRESHOLD_VALUE,
                'notification_score_threshold': settings.DEFAULT_SCORE_THRESHOLD_VALUE,
                'sample_ttl': settings.SAMPLE_TTL,
                'activity_ttl': settings.ACTIVITY_TTL
            })

        with transaction.atomic():
            workspace = WorkspaceManager.create_workspace(title=title, config=config)
            locked_user = User.objects.select_for_update().get(id=user.id)
            locked_workspace = Workspace.objects.select_for_update().get(id=workspace.id)
            AccessManager.create_access(user=locked_user, workspace=locked_workspace, permissions=Access.ADMIN)

            if WorkspaceManager.is_retail(workspace):
                LabelManager.create_default_labels(str(workspace.id))
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


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess])
    def update_workspace_config(root, info: Info,
                                workspace_config: WorkspaceConfigUpdateInput) -> WorkspaceConfigUpdateOutput:
        with transaction.atomic():
            workspace = WorkspaceManager.get_workspace(get_workspace_id(info))

            ws_config = delete_none_from_dict(dataclasses.asdict(workspace_config))
            WorkspaceManager.update_workspace_config(workspace, ws_config)

            workspace.refresh_from_db()

        return WorkspaceConfigUpdateOutput(ok=True, workspace=workspace)
