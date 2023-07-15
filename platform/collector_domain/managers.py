import datetime
import json
import logging
import uuid
from enum import Enum
from typing import Union, List, Tuple, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet, Q

from collector_domain.models import Camera, Agent, AttentionArea
from label_domain.models import Label
from licensing.common_managers import LicensingCommonEvent
from platform_lib.exceptions import LicenseNotExist, LicenseLimitAttribute, LimitException
from platform_lib.utils import UsageAnalytics
from user_domain.models import Workspace
from collector_domain.models import AgentIndexEvent

logger = logging.getLogger(__name__)


class CameraManager:
    def __init__(self, camera_id: Union[str, uuid.UUID], workspace_id: Union[str, uuid.UUID]):
        self.camera = Camera.objects.get(id=camera_id, workspace_id=workspace_id)

    def get_camera(self) -> Camera:
        return self.camera

    @transaction.atomic
    def update_camera_info(self, info: dict) -> bool:
        locked_camera = Camera.objects.select_for_update().get(id=self.camera.id)
        try:
            locked_camera.info.update(info)
            locked_camera.save()
            self.camera = locked_camera
            return True
        except Exception as ex:
            print(ex)
            return False

    def add_camera_location(self, label: Label) -> bool:
        try:
            if not self.verify_label(label):
                return False

            self.camera.locations.add(label)
            return True
        except Exception as ex:
            print(ex)
            return False

    def remove_camera_location(self, label: Label) -> bool:
        try:
            if not self.verify_label(label):
                return False

            self.camera.locations.remove(label)
            return True
        except Exception as ex:
            print(ex)
            return False

    @classmethod
    @transaction.atomic
    def create_camera(cls,
                      workspace: Workspace,
                      info: dict,
                      agent: Optional[Agent] = None,
                      label: Optional[Label] = None,
                      standalone: bool = True) -> Camera:
        camera = Camera.objects.create(workspace=workspace, info=info, agent=agent)
        if label and cls.verify_label(label):
            camera.locations.add(label)

        if standalone:
            try:
                lic_e_man = LicensingCommonEvent(workspace_id=str(workspace.id))
                lic_e_man.create_cameras(Camera.objects.filter(workspace=workspace).count())
            except LicenseLimitAttribute:
                raise LimitException('0x6245cd00', 'Camera limit exceeded')

        return camera

    @classmethod
    @transaction.atomic
    def delete_cameras(cls, cameras: QuerySet, workspace: Workspace, standalone: bool = True) -> bool:
        deleted, _ = cameras.select_for_update().delete()

        if standalone:
            lic_e_man = LicensingCommonEvent(workspace_id=str(workspace.id))
            lic_e_man.delete_cameras(operation_diff_n=deleted)

        return bool(deleted)

    @classmethod
    def verify_label(cls, label: Label) -> bool:
        return label.type == Label.LOCATION

    @staticmethod
    def get_camera_title(camera_id: str) -> Optional[str]:
        camera = Camera.objects.all(Q(is_active__in=[True, False], id=camera_id)).first()
        return camera.info.get("title")


class AttentionAreaManager:
    def __init__(self, attention_area__id: str):
        self.attention_area = AttentionArea.objects.get(id=attention_area__id)

    def get_attention_area(self) -> AttentionArea:
        return self.attention_area

    def change_attention_area_info(self, info: dict) -> bool:
        try:
            self.attention_area.info = info
            self.attention_area.save()
            return True
        except Exception as ex:
            print(ex)
            return False

    def add_attention_area_type(self, label: Label) -> bool:
        try:
            if not self.verify_label(label):
                return False

            self.attention_area.area_types.add(label)
            return True
        except Exception as ex:
            print(ex)
            return False

    def remove_attention_area_type(self, label: Label) -> bool:
        try:
            if not self.verify_label(label):
                return False

            self.attention_area.area_types.remove(label)
            return True
        except Exception as ex:
            print(ex)
            return False

    @staticmethod
    def create_attention_area(workspace: Workspace, camera: Camera, info: dict = None) -> Agent:
        if info is None:
            info = {}
        attention_area = AttentionArea.objects.create(workspace=workspace, camera=camera, info=info)
        return attention_area

    @staticmethod
    def delete_attention_areas(ids: list, workspace: Workspace) -> bool:
        deleted, _ = AttentionArea.objects.select_for_update().filter(workspace=workspace, id__in=ids).delete()
        return bool(deleted)

    @classmethod
    def verify_label(cls, label: Label) -> bool:
        return label.type == "area_type"


class AgentManager:
    status_field_name = "status"
    last_active_time_field_name = "last_active_time"
    title_field_name = "title"

    class AgentStatus(str, Enum):
        ACTIVE = "active"
        INACTIVE = "inactive"

    def __init__(self, agent_id: Union[str, uuid.UUID]):
        self.agent = Agent.objects.get(id=agent_id)

    def get_agent(self) -> Agent:
        return self.agent

    @staticmethod
    def get_locked_agent(agent_id: Union[str, uuid.UUID]) -> Agent:
        return Agent.objects.select_for_update().get(id=agent_id)

    def get_agent_status(self) -> str:
        return self.agent.info.get(self.status_field_name, self.AgentStatus.INACTIVE)

    def get_agent_last_active_time(self) -> str:
        return self.agent.info.get(self.last_active_time_field_name, None)

    @classmethod
    def update_or_activate_agent(cls, agent_id: Union[str, uuid.UUID]):
        """
        Set agent status in active and update last active time
        """
        agent = cls.get_locked_agent(agent_id)
        agent.info[cls.status_field_name] = cls.AgentStatus.ACTIVE
        agent.info[cls.last_active_time_field_name] = datetime.datetime.utcnow().isoformat()
        agent.save()

    @classmethod
    def deactivate_agent(cls, agent_id: Union[str, uuid.UUID]):
        """
        Set agent status in inactive
        """
        agent = cls.get_locked_agent(agent_id)
        agent.info[cls.status_field_name] = cls.AgentStatus.INACTIVE
        agent.save()

    def check_agent_status(self) -> bool:
        """
        Check status of agent.
        Get last active period from agent info and compare current time + AGENT_INACTIVE_PERIOD_SECONDS with it.
        If last active period less or equal then true else false.
        If last active period not presented in info return false

        Returns
        -------
        bool
            Result of checking agent status
        """
        agent_inactive_period = settings.AGENT_INACTIVE_PERIOD_SECONDS
        last_update_time_string = self.agent.info.get(self.last_active_time_field_name, None)

        # Return inactive agent status if not found suitable last active time field
        if not last_update_time_string:
            return False

        last_update_time = datetime.datetime.fromisoformat(last_update_time_string)
        current_time = datetime.datetime.utcnow()

        return current_time <= last_update_time + datetime.timedelta(0, agent_inactive_period)

    @classmethod
    def change_agent_title(cls, agent_id: Union[str, uuid.UUID], title: str) -> Tuple[bool, Optional[Agent]]:
        try:
            agent = cls.get_locked_agent(agent_id)
            agent.info[cls.title_field_name] = title
            agent.save()
            return True, agent
        except Agent.DoesNotExist as ex:
            print(ex)
            return False, None

    @classmethod
    def create_agent(cls, workspace: Workspace, title: str) -> Agent:
        info = {
            cls.title_field_name: title,
            cls.status_field_name: cls.AgentStatus.INACTIVE
        }
        agent = Agent.objects.create(workspace=workspace, info=info)

        UsageAnalytics(
            operation='agent_create',
            username=workspace.accesses.first().user.username,
            meta={'device': str(agent.id)}
        ).start()
        return agent

    @staticmethod
    def get_all_agents() -> QuerySet[Agent]:
        return Agent.objects.filter(is_active=True)

    @staticmethod
    def delete_agents(ids: list, workspace: Workspace, standalone: bool = True) -> bool:
        agents = Agent.objects.select_for_update().filter(workspace=workspace, id__in=ids).prefetch_related('cameras')
        if agents.exists():
            for agent in agents:
                CameraManager.delete_cameras(agent.cameras.all(), workspace, standalone)
                agent.delete()
            return True
        return False

    @staticmethod
    @transaction.atomic
    def add_cameras(agent_id: uuid.UUID, camera_ids: List[uuid.UUID], workspace: Workspace) -> bool:
        agent = Agent.objects.select_for_update().get(workspace=workspace, id=agent_id)
        agent.cameras.add(*Camera.objects.filter(workspace=workspace, id__in=camera_ids))
        agent.save()
        return agent

    @staticmethod
    @transaction.atomic
    def remove_cameras(agent_id: uuid.UUID, camera_ids: List[uuid.UUID], workspace: Workspace) -> bool:
        agent = Agent.objects.select_for_update().get(workspace=workspace, id=agent_id)
        agent.cameras.remove(*Camera.objects.filter(workspace=workspace, id__in=camera_ids))
        agent.save()
        return agent


class AgentIndexEventManager:
    def __init__(self, workspace_id):
        self.workspace_id = workspace_id

    def __create(self, type: str, profile_id: str, person_id: str, data: dict):
        return AgentIndexEvent.objects.create(
            type=type,
            workspace_id=self.workspace_id,
            profile_id=profile_id,
            person_id=person_id,
            data=data
        )

    def add_profile(self, profile_id: str, person_id: str, data: dict):
        return self.__create('add', profile_id, person_id, data)

    def update_profile(self, profile_id: str, person_id: str, data: dict):
        return self.__create('upd', profile_id, person_id, data)

    def delete_profile(self, profile_id: str, person_id: str):
        return self.__create('del', profile_id, person_id, {})
