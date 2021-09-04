from typing import List, Optional

import strawberry
from strawberry import auto
from django.conf import settings

from label_domain.models import Label
from platform_lib.types import JSONString
from user_domain import models


@strawberry.django.type(models.User)
class UserType:
    username: auto
    email: auto
    first_name: auto
    last_name: auto


@strawberry.type
class AccessOutput:
    @staticmethod
    def resolve_token(root, info):
        return str(root.id)

    @staticmethod
    def resolve_workspace_is_active(root, info):
        return root.workspace.config.get('is_active', False)

    @staticmethod
    def resolve_workspace_title(root, info):
        return root.workspace.title

    @staticmethod
    def resolve_username(root, info):
        return root.user.username if root.user is not None else None

    id: strawberry.ID
    token: str = strawberry.field(resolver=resolve_token)
    workspace_is_active: bool = strawberry.field(resolver=resolve_workspace_is_active)
    workspace_title: str = strawberry.field(resolver=resolve_workspace_title)
    username: str = strawberry.field(resolver=resolve_username)


@strawberry.type
class WorkspaceType:

    @staticmethod
    def resolve_agents_count(root, info):
        return root.agents.count()

    @staticmethod
    def resolve_active_agents_count(root, info):
        return root.agents.filter(is_active=True).count()

    @staticmethod
    def resolve_profiles_count(root, info):
        return root.profiles.count()

    @staticmethod
    def resolve_profile_groups_count(root, info):
        return root.labels.filter(type=Label.PROFILE_GROUP).count()

    @staticmethod
    def resolve_persons_count(root, info):
        return root.persons.count()

    @staticmethod
    def resolve_plan_name(root, info):
        return root.plan_name

    @staticmethod
    def resolve_checkout_upgrade(root, info):
        return settings.CHECKOUT_UPGRADE.format(root.id)

    @staticmethod
    def resolve_detail_card(root, info):
        return settings.DETAIL_CARD.format(root.id)

    @staticmethod
    def resolve_active(root, info):
        return root.config.get('is_active', False)

    @staticmethod
    def resolve_access(root, info):
        return root.accesses.all()

    @staticmethod
    def resolve_auto_creation_enabled(root, info):
        return False  # workspace.get_custom_resolver('auto_creation_enabled')(workspace, info)

    @staticmethod
    def resolve_updating_profile_sample_enabled(root, info):
        return False  # workspace.get_custom_resolver('updating_profile_sample_enabled')(workspace, info)

    @staticmethod
    def resolve_template_version(root, info):
        return "none"  # workspace.get_custom_resolver('template_version')(workspace, info)

    @staticmethod
    def resolve_webhook(root, info):
        return ""  # workspace.get_custom_resolver('webhook')(workspace, info)

    @staticmethod
    def resolve_misc_data_fields(root, info):
        return {}  # workspace.get_custom_resolver('misc_data_fields')(workspace, info)

    @staticmethod
    def resolve_validate_templates_for_profile(root, info):
        return False  # workspace.get_custom_resolver('validate_templates_for_profile')(workspace, info)

    id: strawberry.ID
    accesses: List[AccessOutput] = strawberry.field(resolver=resolve_access)
    title: Optional[str]
    config: Optional[JSONString]
    isActive: Optional[bool] = strawberry.field(resolver=resolve_active)
    profilesCount: Optional[int] = strawberry.field(resolver=resolve_profiles_count)
    profileGroupsCount: Optional[int] = strawberry.field(resolver=resolve_profile_groups_count)
    agentsCount: Optional[int] = strawberry.field(resolver=resolve_agents_count)
    # TODO Remove after cognitive update
    devicesCount: Optional[int] = strawberry.field(resolver=resolve_agents_count)
    active_agents_count: Optional[int] = strawberry.field(resolver=resolve_active_agents_count)
    # TODO Remove after cognitive update
    active_devices_count: Optional[int] = strawberry.field(resolver=resolve_active_agents_count)
    detailCard: Optional[str] = strawberry.field(resolver=resolve_detail_card)
    checkoutUpgrade: Optional[str] = strawberry.field(resolver=resolve_checkout_upgrade)
    planName: Optional[str] = strawberry.field(resolver=resolve_plan_name)
    personsCount: Optional[int] = strawberry.field(resolver=resolve_persons_count)
    # TODO Remove after cognitive update
    sessionsCount: Optional[int] = strawberry.field(resolver=resolve_persons_count)


@strawberry.type
class WorkspaceCreateOutput:
    ok: Optional[bool]
    workspace: Optional[WorkspaceType]


@strawberry.input
class WorkspaceConfigInput:
    is_active: Optional[bool]

    def to_dict(self):
        return {"is_active": self.is_active}


@strawberry.type
class WorkspaceConfigOutput:
    is_active: Optional[bool]


@strawberry.type
class WorkspaceConfigSetOutput:
    ok: Optional[bool]
    config: Optional[WorkspaceConfigOutput]
    config_json: Optional[JSONString]


@strawberry.input
class RegistrationInput:
    user_name: str
    user_last_name: str
    user_email: str
    user_password: str
    confirm_password: str


@strawberry.type
class LogoutSuccess:
    ok: bool


@strawberry.type
class LoginSuccess:
    ok: bool
    workspaces: List[WorkspaceType]


@strawberry.type
class LoginError:
    message: str


@strawberry.type
class ElkOutput:
    ok: bool


@strawberry.type(description="Links to analytics")
class AnalyticsOutput:
    retail: Optional[str] = strawberry.field(description="Link to retail analytics", default=None)
    advertising: Optional[str] = strawberry.field(description="Link to advertising analytics", default=None)
