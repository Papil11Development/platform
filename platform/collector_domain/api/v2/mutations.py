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

from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive, IsAccessToken
from platform_lib.exceptions import BadInputDataException, LimitException, BalanceException, InternalException
from collector_domain.api.v2.types import AgentInput, AgentUpdateInput, AgentManageOutput, AgentCreateOutput
from collector_domain.managers import CameraManager, AgentManager
from collector_domain.models import Camera
from platform_lib.types import MutationResult
from platform_lib.utils import get_workspace_id, get_token, get_user, type_desc
from user_domain.models import Workspace, Access


@strawberry.type
class AgentMutation:

    @strawberry.mutation(
        permission_classes=[IsHaveAccess, IsAccessToken, IsWorkspaceActive],
        description="Delete agent by ids"
    )
    def delete_agent(root, info: Info,
                     agent_id: type_desc(Optional[ID], "Agent for deletion id") = None,
                     agent_ids: type_desc(Optional[List[ID]], "Agent for deletion ids") = None) -> MutationResult:
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

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Update agent data")
    def update_agent(root, info: Info,
                     agent_id: type_desc(ID, "Agent for update id"),
                     agent_data: type_desc(AgentUpdateInput, "Agent data for update")) -> AgentManageOutput:
        camera = Camera.objects.get(agent=str(agent_id))
        camera_manager = CameraManager(camera_id=str(camera.id))

        with transaction.atomic():
            ok, agent = AgentManager.change_agent_title(agent_id=agent_id, title=agent_data.title)
            camera_manager.change_camera_title(title=agent_data.title)

        return AgentManageOutput(ok=ok, agent=agent)

    @strawberry.mutation(
        permission_classes=[IsHaveAccess, IsAccessToken, IsWorkspaceActive],
        description="Create new agent"
    )
    def create_agent(root, info: Info,
                     agent_data: type_desc(AgentInput, "Agent data for creation")) -> AgentCreateOutput:
        extra = agent_data.extra or {}

        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)
        device_count = workspace.agents.count()
        payment_permission = extra.get('payment_permission', False)

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

        with transaction.atomic():
            agent = AgentManager.create_agent(workspace=workspace, title=agent_data.title)
            _ = CameraManager.create_camera(workspace=workspace,
                                            title=agent_data.title,
                                            agent=agent,
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
