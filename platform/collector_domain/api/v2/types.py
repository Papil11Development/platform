import datetime
from typing import List, Optional
import strawberry
from strawberry import ID
from strawberry.types import Info

from collector_domain.managers import AgentManager
from platform_lib.types import JSON, MutationResult
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


# model interpretation types


@strawberry.type(description="Information about the agent that is the information collection tool,"
                             " its token, name, status, etc.")
class AgentOutput:
    description_name = "agents"

    @strawberry.field(description='Agent token')
    def token(root, info: Info) -> ID:
        return root.id

    @strawberry.field(description='Ids of agent cameras')
    def cameras_ids(root, info: Info) -> Optional[List[ID]]:
        return [camera.id for camera in root.cameras.all(Q(is_active__in=[True, False]))]

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


# output types

@strawberry.type(description="Information about the updated agent")
class AgentManageOutput(MutationResult):
    agent: AgentOutput = strawberry.field(description="Agent object")


@strawberry.type(description="Information on the agent created, the next payment date and the value of the payment"
                             " if the next agent requires payment")
class AgentCreateOutput(AgentManageOutput):
    channel_cost: Optional[str] = strawberry.field(description="The cost of the channel per month")
    writeoff_date: Optional[str] = strawberry.field(description="Next payment date")


# collections

AgentsCollection = strawberry.type(get_collection(AgentOutput, 'AgentsCollection'),
                                   description="Filtered agent collection and total agents count")

# field maps

agents_map = {
    'groupsIds': 'profile_groups__id__in',
    'creationDate': 'creation_date',
    'lastModified': 'last_modified'
}
