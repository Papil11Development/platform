import datetime
from typing import List, Optional
from uuid import UUID
import strawberry
from strawberry import ID
from strawberry.types import Info

from collector_domain.managers import AgentManager
from platform_lib.types import JSON, MutationResult, ExtraFieldInput
from platform_lib.utils import get_collection
from django.db.models import Q


# input types


@strawberry.input(description="Information needed to create an agent")
class AgentInput:
    title: Optional[str] = strawberry.field(default="", description="Agent title")
    extra: Optional[JSON] = strawberry.field(description="Extra agent information", default=None)


@strawberry.input(description="Information needed to update the agent")
class AgentUpdateInput:
    title: str = strawberry.field(default="", description="Agent title")


@strawberry.input(description="Information needed for camera creation")
class CameraInput:
    fields: Optional[List[ExtraFieldInput]] = strawberry.field(default=None)
    agent_id: Optional[ID] = strawberry.field(description="ID of the agent to link the camera to", default=None)


# model interpretation types

@strawberry.type(description="Information about the camera that is the information collection tool.")
class CameraOutput:
    description_name = "cameras"

    @strawberry.field(description="Info about camera")
    def info(self) -> JSON:
        return self.info

    id: ID
    creation_date: datetime.datetime = strawberry.field(description="Camera creation date")
    last_modified: datetime.datetime = strawberry.field(description="Last camera modification date")


@strawberry.type(description="Information about the agent that is the information collection tool,"
                             " its token, name, status, etc.")
class AgentOutput:
    description_name = "agents"

    @strawberry.field(description='Agent token')
    def token(root, info: Info) -> ID:
        return root.id

    @strawberry.field(description='Ids of agent cameras')
    def cameras_ids(root, info: Info) -> Optional[List[ID]]:
        return [camera.id for camera in root.cameras.all()]

    @strawberry.field(description='Agent cameras')
    def cameras(root, info: Info) -> Optional[List[CameraOutput]]:
        return root.cameras.all()

    @strawberry.field(description='Agent title')
    def title(root, info: Info) -> Optional[str]:
        return root.info.get("title")

    @strawberry.field(description='Agent work status')
    def agent_status(root, info) -> str:
        agent_manager = AgentManager(str(root.id))
        return agent_manager.get_agent_status()

    @strawberry.field(description='Agent last work time')
    def agent_last_active_time(root, info) -> Optional[str]:
        agent_manager = AgentManager(str(root.id))
        return agent_manager.get_agent_last_active_time()

    @strawberry.field(description="The object is in the archive")
    def archived(root) -> bool:
        return not root.is_active

    id: ID

    creation_date: datetime.datetime = strawberry.field(description="Agent creation date")
    last_modified: datetime.datetime = strawberry.field(description="Last agent modification date")


@strawberry.type(description="Information about agent")
class AgentInfo(AgentOutput):
    @strawberry.field(description='Agent workspace id')
    def workspace_id(root) -> ID:
        return root.workspace_id

# output types


@strawberry.type(description="Information about the updated agent")
class AgentManageOutput(MutationResult):
    agent: AgentOutput = strawberry.field(description="Agent object")


@strawberry.type(description="Information about the updated camera")
class CameraManageOutput(MutationResult):
    camera: CameraOutput = strawberry.field(description="Camera object")


@strawberry.type(description="Information on the agent created, the next payment date and the value of the payment"
                             " if the next agent requires payment")
class AgentCreateOutput(AgentManageOutput):
    channel_cost: Optional[str] = strawberry.field(description="The cost of the channel per month")
    writeoff_date: Optional[str] = strawberry.field(description="Next payment date")


@strawberry.type(description="Workspace collector settings")
class CollectorSettingsType:
    id: UUID
    camera_fields: JSON


# collections

AgentsCollection = strawberry.type(get_collection(AgentOutput, 'AgentsCollection'),
                                   description="Filtered agent collection and total agents count")

CamerasCollection = strawberry.type(get_collection(CameraOutput, 'CamerasCollection'),
                                    description="Filtered camera collection and total cameras count")

# field maps

agents_map = {
    'groupsIds': 'profile_groups__id__in',
    'creationDate': 'creation_date',
    'lastModified': 'last_modified'
}
