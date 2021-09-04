import datetime
from typing import List, Optional
import strawberry
from strawberry import ID

from collector_domain.managers import AgentManager
from label_domain.api.v1.types import LocationOutput
from platform_lib.types import JSONString, MutationResult
from platform_lib.utils import get_collection


# input types


@strawberry.input
class AgentInput:
    title: Optional[str] = strawberry.field(default="")
    auto_create_profiles: Optional[bool] = False
    extra: Optional[JSONString] = strawberry.field(default_factory=dict)


@strawberry.input
class AgentUpdateInput:
    title: str


# model interpretation types


@strawberry.type
class AttentionAreaOutput:
    @staticmethod
    def resolve_title(root, info):
        return root.info.get('title')

    @staticmethod
    def resolve_camera_id(root, info):
        return root.camera.id

    @staticmethod
    def resolve_camera_roi_id(root, info):
        return root.info.get('camera_roi_id')

    id: ID = strawberry.field(description='Roi id')
    camera_roi_id: ID = strawberry.field(resolver=resolve_camera_roi_id, description='Agent roi id')
    title: str = strawberry.field(resolver=resolve_title, description='Roi title')
    info: JSONString = strawberry.field(description='Info of a roi')
    camera_id: ID = strawberry.field(resolver=resolve_camera_id, description='Id of a camera')
    creation_date: datetime.datetime = strawberry.field()
    last_modified: datetime.datetime = strawberry.field()


@strawberry.type
class CameraOutput:
    """Represents the camera created by a client."""
    """Camera automatically generates the information about the matching operations."""

    @staticmethod
    def resolve_location_id(root, info):
        return root.locations.all().first().id if root.locations.all() else None

    @staticmethod
    def resolve_agent_id(root, info):
        return root.agent.id

    @staticmethod
    def resolve_attention_areas(root, info):
        return [attention_area for attention_area in root.attention_areas.all()]

    id: ID = strawberry.field(description='Camera id')
    title: str = strawberry.field(description='Title of a camera')
    rois: Optional[List[AttentionAreaOutput]] = strawberry.field(resolver=resolve_attention_areas,
                                                                 description='Related Rois')
    location_id: Optional[ID] = strawberry.field(resolver=resolve_location_id)
    agent_id: Optional[ID] = strawberry.field(resolver=resolve_agent_id)
    creation_date: Optional[datetime.datetime] = strawberry.field()
    last_modified: Optional[datetime.datetime] = strawberry.field()


@strawberry.type
class AgentOutput:
    """Represents the agent created by a client."""
    """Agent automatically generates the information about the matching operations."""

    @staticmethod
    def resolve_token(root, info) -> str:
        return str(root.id)

    @staticmethod
    def resolve_agent_status(root, info) -> str:
        agent_manager = AgentManager(str(root.id))
        return agent_manager.get_agent_status()

    @staticmethod
    def resolve_agent_last_active_time(root, info) -> Optional[str]:
        agent_manager = AgentManager(str(root.id))
        return agent_manager.get_agent_last_active_time()

    @staticmethod
    def resolve_cameras_ids(root, info):
        try:
            return [camera.id for camera in root.cameras.all()]
        except Exception as ex:
            print(ex)
            return root.camerasIds

    @staticmethod
    def resolve_title(root, info):
        return root.info.get("title")

    @staticmethod
    def resolve_creation_date(root, info):
        return root.creation_date

    @staticmethod
    def resolve_last_modified(root, info):
        return root.last_modified

    id: ID
    token: str = strawberry.field(resolver=resolve_token, description='Agent token')
    title: str = strawberry.field(resolver=resolve_title, description='Title of a agent')
    cameras_ids: List[ID] = strawberry.field(resolver=resolve_cameras_ids, description='Ids of agent cameras')
    status: str = strawberry.field(resolver=resolve_agent_status, description='Connection status')
    last_active_time: Optional[str] = strawberry.field(resolver=resolve_agent_last_active_time,
                                                       description='Last active time')
    creation_date: datetime.datetime = strawberry.field(resolver=resolve_creation_date)
    last_modified: datetime.datetime = strawberry.field(resolver=resolve_last_modified)


# output types


@strawberry.type
class LocationManageOutput(MutationResult):
    location: LocationOutput = strawberry.field(description="Location object")


@strawberry.type
class AgentManageOutput(MutationResult):
    agent: AgentOutput = strawberry.field(description="Agent object")


@strawberry.type
class AgentCreateOutput(AgentManageOutput):
    channel_cost: Optional[str] = strawberry.field()
    writeoff_date: Optional[str] = strawberry.field()


# collections

AgentsCollection = strawberry.type(get_collection(AgentOutput, 'AgentsCollection'))
CamerasCollection = strawberry.type(get_collection(CameraOutput, 'CamerasCollection'))
AttentionAreasCollection = strawberry.type(get_collection(AttentionAreaOutput, 'AttentionAreasCollection'))


# field maps

device_map = {
    'groupsIds': 'profile_groups__id__in',
    'creationDate': 'creation_date',
    'lastModified': 'last_modified'
}

camera_map = {
    'groupsIds': 'profile_groups__id__in'
}

roi_map = {
    'cameraId': 'camera__id'
}
