import datetime
import json
from typing import List, Optional

import requests
import strawberry
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from strawberry import ID
from strawberry.types import Info

from label_domain.managers import LabelManager
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive, IsAccessToken
from platform_lib.exceptions import BadInputDataException, LimitException, BalanceException, InternalException
from collector_domain.api.v1.types import AgentInput, AgentUpdateInput, \
    LocationManageOutput, AgentManageOutput, AgentCreateOutput
from collector_domain.managers import CameraManager, AgentManager
from collector_domain.models import Camera
from platform_lib.types import MutationResult
from platform_lib.utils import get_workspace_id, get_user
from user_domain.models import Workspace


@strawberry.type
class LocationLinkMutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def add_camera_to_location(self, info: Info,
                               location_id: ID,
                               camera_id: Optional[ID]) -> LocationManageOutput:
        manager = CameraManager(str(camera_id))
        label = LabelManager.get_label_by_id(label_id=location_id)
        ok = manager.add_camera_location(label=label)

        return LocationManageOutput(ok=ok, location=label)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def delete_camera_from_location(self, info: Info,
                                    location_id: ID,
                                    camera_id: Optional[ID]) -> LocationManageOutput:
        manager = CameraManager(str(camera_id))
        label = LabelManager.get_label_by_id(label_id=location_id)
        ok = manager.remove_camera_location(label=label)

        return LocationManageOutput(ok=ok, location=label)


@strawberry.type
class AgentMutation:
    @strawberry.mutation(permission_classes=[IsHaveAccess, IsAccessToken, IsWorkspaceActive])
    def delete_agent(root,
                     info: Info,
                     agent_id: Optional[ID] = "",
                     agent_ids: Optional[List[ID]] = None) -> MutationResult:
        ok = False

        if bool(agent_id) == bool(agent_ids):
            raise BadInputDataException("0xe509f74d")

        ids = [agent_id] if agent_id else agent_ids

        workspace_id = get_workspace_id(info)
        workspace = Workspace.objects.get(id=workspace_id)
        user = get_user(info=info)
        standalone = user.groups.filter(name=settings.STANDALONE_GROUP).exists()
        with transaction.atomic():
            deleted = AgentManager.delete_agents(ids=ids, workspace=workspace, standalone=standalone)
        if deleted:
            ok = True
        return MutationResult(ok=ok)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def change_agent(root, agent_id: ID, agent_data: AgentUpdateInput) -> AgentManageOutput:
        camera = Camera.objects.get(agent=str(agent_id))
        camera_manager = CameraManager(camera_id=str(camera.id))
        with transaction.atomic():
            ok, agent = AgentManager.change_agent_title(agent_id=agent_id, title=agent_data.title)
            camera_manager.change_camera_title(title=agent_data.title)
        return AgentManageOutput(ok=ok, agent=agent)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsAccessToken, IsWorkspaceActive])
    def create_agent(root, info: Info, agent_data: AgentInput) -> AgentCreateOutput:
        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        device_count = workspace.agents.filter(is_active=True).count()
        payment_permission = agent_data.extra.get('payment_permission', False)

        payment_data = {}

        user = get_user(info=info)
        standalone = user.groups.filter(name=settings.STANDALONE_GROUP).exists()
        if not standalone:
            info_cognitive = AgentMutation.__cognitive_add_device(str(workspace.id),
                                                                  'buy' if payment_permission else 'add',
                                                                  device_count)
            payment_data = {
                'channel_cost': info_cognitive.get('channel_cost'),
                'writeoff_date': AgentMutation.__convert_date(info_cognitive.get('writeoff_date'),
                                                              '%Y-%m-%dT%H:%M:%S.%f%z')
            }
        elif device_count >= workspace.config.get("agent_limit", 3) and not settings.IS_ON_PREMISE:
            raise LimitException('0x1fdc14b6', 'Agent limit exceeded')

        with transaction.atomic():
            agent = AgentManager.create_agent(workspace=workspace, title=agent_data.title)
            _ = CameraManager.create_camera(workspace=workspace, title=agent_data.title, agent=agent,
                                            standalone=standalone)

        return AgentCreateOutput(agent=agent,
                                 ok=True,
                                 channel_cost=payment_data.get("channel_cost", None),
                                 writeoff_date=payment_data.get("writeoff_date", None))

    @staticmethod
    def __cognitive_add_device(workspace_id: str, action: str = 'add', device_count: int = None):
        response = requests.post(
            url=f'{settings.LICENSE_SERVER_URL}/api/{settings.LICENSING_PRODUCT_NAME}/device-billing/',
            data={'workspace_id': workspace_id, 'action': action, 'device_count': device_count}
        )
        ans = response.json()
        ok = ans.get('ok', False)
        errors = ans.get('errors')
        code = ans.get('code')
        details = ans.get('details', {})

        info = {
            'channel_cost': ans.get('channel_cost'),
            'writeoff_date': ans.get('writeoff_date')
        }

        if not ok:
            if code == '0x1fdc14b6':
                limit = details['devices_limit']
                price = details['device_cost']
                raise LimitException('0x1fdc14b6', json.dumps({
                    'edge_limit': limit,
                    'amount': price,
                    'channel_cost': info['channel_cost'],
                    'writeoff_date': info['writeoff_date']
                }))
            elif code == '0x50028bd4':
                raise BalanceException('0x50028bd4')
            else:
                errors = {'errors': errors, 'details': details}
                raise InternalException('0x312cf586', json.dumps(errors))

        return info

    @staticmethod
    def __convert_date(value, fmt):
        return datetime.datetime.strptime(value, fmt).isoformat()
