from typing import List, Optional

import strawberry
from django.conf import settings
from strawberry import ID
from strawberry.types import Info

from label_domain.models import Label
from platform_lib.types import JSON, JSONString, MutationResult
from user_domain.models import Workspace


@strawberry.type(description="Information on user access to a specific workspace")
class AccessOutput:
    id: ID

    @strawberry.field(description="Access token")
    def token(root, info: Info) -> ID:
        return root.id

    @strawberry.field(description="Access workspace status")
    def workspace_is_active(root, info: Info) -> bool:
        return root.workspace.config.get('is_active', False)

    @strawberry.field(description="Access workspace title")
    def workspace_title(root, info: Info) -> str:
        return root.workspace.title

    @strawberry.field(description="Access owner username")
    def username(root, info: Info) -> str:
        return root.user.username if root.user is not None else None


@strawberry.type(description="Information about the user's workspace, e.g. number of active agents, profiles, etc.")
class WorkspaceType:
    id: ID
    title: str = strawberry.field(description="Workspace title")
    config: JSON = strawberry.field(description="Workspace config. Witch contains workspace settings and info")

    @strawberry.field(description="List of accesses")
    def accesses(root, info: Info) -> List[AccessOutput]:
        return root.accesses.all()

    @strawberry.field(description="Count of agents in workspace")
    def agents_count(root, info: Info) -> int:
        return root.agents.count()

    @strawberry.field(description="Count of active agents in workspace")
    def active_agents_count(root, info: Info) -> int:
        return root.agents.filter(is_active=True).count()

    @strawberry.field(description="Count of active agents in workspace")
    def active_devices_count(root, info: Info) -> int:
        return root.agents.filter(is_active=True).count()

    @strawberry.field(description="Count of profiles in workspace")
    def profiles_count(root, info: Info) -> int:
        return root.profiles.count()

    @strawberry.field(description="Count of profile groups in workspace")
    def profile_groups_count(root, info: Info) -> int:
        return root.labels.filter(type=Label.PROFILE_GROUP).count()

    @strawberry.field(description="Workspace status")
    def active(root, info: Info) -> bool:
        return root.config.get('is_active', False)

    @strawberry.field(description="Workspace payment plan name")
    def plan_name(root, info: Info) -> Optional[str]:
        return root.plan_name

    @strawberry.field(description="Url for upgrade workspace payment plan")
    def checkout_upgrade(root, info: Info) -> Optional[str]:
        return settings.CHECKOUT_UPGRADE.format(root.id)

    @strawberry.field(description="Url for workspace payment plan details")
    def detail_card(root, info: Info) -> Optional[str]:
        return settings.DETAIL_CARD.format(root.id)


@strawberry.type(description="Information about created workspace")
class WorkspaceCreateOutput(MutationResult):
    workspace: Optional[WorkspaceType] = strawberry.field(description="Created workspace")


@strawberry.input
class WorkspaceConfigInput:
    is_active: Optional[bool]

    def to_dict(self):
        return {"is_active": self.is_active}


@strawberry.input
class WorkspaceConfigUpdateInput:
    activity_score_threshold: Optional[float] = strawberry.field(
        description="The threshold for matching activities to persons",
        default=None
    )
    notification_score_threshold: Optional[float] = strawberry.field(
        description="Threshold for creating notifications by person presence",
        default=None
    )


@strawberry.type
class WorkspaceConfigOutput:
    is_active: Optional[bool]


@strawberry.type
class WorkspaceConfigSetOutput:
    ok: Optional[bool]
    config: Optional[WorkspaceConfigOutput]
    config_json: Optional[JSONString]


@strawberry.type
class WorkspaceConfigUpdateOutput:
    ok: bool
    workspace: WorkspaceType


@strawberry.type(description="Links to analytics")
class AnalyticsOutput:
    retail: Optional[str] = strawberry.field(description="Link to retail analytics", default=None)
    advertising: Optional[str] = strawberry.field(description="Link to advertising analytics", default=None)


@strawberry.input(description="Info for register new user")
class RegistrationInput:
    email: str = strawberry.field(description="User email")
    password: str = strawberry.field(description="User password")
    confirm_password: str = strawberry.field(description="Confirm password")
    first_name: Optional[str] = strawberry.field(description="User first name", default=None)
    last_name: Optional[str] = strawberry.field(description="User last name", default=None)


@strawberry.type(description="Object that represent user")
class UserType:
    username: str = strawberry.field(description="User name", default=None)
    email: str = strawberry.field(description="User email", default=None)
    first_name: str = strawberry.field(description="User first name", default=None)
    last_name: str = strawberry.field(description="User last name", default=None)

    @strawberry.field(description="User workspaces")
    def workspaces(root) -> List[WorkspaceType]:
        accesses = root.accesses.all()
        return Workspace.objects.filter(accesses__in=accesses)


@strawberry.type(description="Information about user that logged-in and login status")
class LoginResult(MutationResult):
    me: UserType = strawberry.field(description="Information about logged-in user")


@strawberry.type(description="Result of success registration")
class RegistrationOutput(MutationResult):
    user: UserType = strawberry.field(description="Created user")


@strawberry.input(description="Information needed for change password")
class ChangePasswordInput:
    old_password: str = strawberry.field(description="Old password")
    new_password: str = strawberry.field(description="New password")
    confirm_new_password: str = strawberry.field(description="Confirm new password")


@strawberry.input(description="Information needed for reset password")
class ResetPasswordInput:
    user_id: str = strawberry.field(description="User id")
    confirmation_token: str = strawberry.field(description="Confirmation token")
    new_password: str = strawberry.field(description="New password")
    confirm_new_password: str = strawberry.field(description="Confirm new password")


@strawberry.input(description="Information needed for confirm registration")
class ConfirmationInput:
    user_id: str = strawberry.field(description="User id")
    confirmation_token: str = strawberry.field(description="Confirmation token")
