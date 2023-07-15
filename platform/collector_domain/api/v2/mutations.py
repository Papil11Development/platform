import datetime
import json
from typing import List, Optional

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F, Func, Value, JSONField

import strawberry
from strawberry import ID
from strawberry.types import Info
from collector_domain.api.v1.types import AgentOutput

from collector_domain.api.v2.types import AgentInput, AgentUpdateInput, AgentManageOutput, AgentCreateOutput, \
    CameraManageOutput, CameraInput
from collector_domain.managers import CameraManager, AgentManager
from collector_domain.models import Camera, Agent, CollectorSettings

from user_domain.models import Workspace

from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive, IsAccessToken
from platform_lib.exceptions import BadInputDataException, LimitException, BalanceException, InternalException
from platform_lib.types import MutationResult, ModifyExtraField, FieldsModifyResult
from platform_lib.utils import get_workspace_id, get_user, type_desc


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

        with transaction.atomic():
            ok, agent = AgentManager.change_agent_title(agent_id=agent_id, title=agent_data.title)

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

    @strawberry.mutation(
        permission_classes=[IsHaveAccess, IsAccessToken, IsWorkspaceActive],
        description="Create new camera"
    )
    def create_camera(root, info: Info,
                      camera_data: type_desc(CameraInput, "Camera data for creation")) -> CameraManageOutput:
        workspace_id = get_workspace_id(info=info)
        workspace = Workspace.objects.get(id=workspace_id)

        user = get_user(info=info)
        standalone = user.groups.filter(name=settings.STANDALONE_GROUP).exists()

        with transaction.atomic():
            p_settings, created = CollectorSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                p_settings.camera_fields = settings.REQUIRED_CAMERA_FIELDS
                p_settings.save()
            available_fields = p_settings.camera_fields

            camera_info = {}
            if camera_data.fields:
                camera_info = {item.name.lower(): item.value or None for item in camera_data.fields}

                missed_fields = set(camera_info) - set(available_fields)
                if missed_fields:
                    raise Exception(f"Fields are unavailable: ({missed_fields})")

            camera = CameraManager.create_camera(
                workspace=workspace, info=camera_info, standalone=standalone
            )
            if camera_data.agent_id:
                AgentManager.add_cameras(camera_data.agent_id, [camera.id], workspace_id)

        return CameraManageOutput(camera=camera, ok=True)

    @strawberry.mutation(
        permission_classes=[IsHaveAccess, IsAccessToken, IsWorkspaceActive],
        description="Delete cameras by ids"
    )
    def delete_cameras(root, info: Info,
                       camera_ids: type_desc(List[ID], "Camera for deletion ids") = None) -> MutationResult:
        workspace_id = get_workspace_id(info)
        workspace = Workspace.objects.get(id=workspace_id)

        user = get_user(info=info)
        standalone = user.groups.filter(name=settings.STANDALONE_GROUP).exists()

        with transaction.atomic():
            cameras_qs = Camera.objects.select_for_update().filter(id__in=camera_ids)
            deleted = CameraManager.delete_cameras(cameras_qs, workspace=workspace, standalone=standalone)
        return MutationResult(ok=deleted)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Update agent data")
    def update_camera(root, info: Info,
                      camera_id: type_desc(ID, "ID of Camera for update"),
                      camera_data: type_desc(CameraInput, "Camera data for update")) -> CameraManageOutput:

        workspace_id = get_workspace_id(info=info)

        with transaction.atomic():
            camera = Camera.objects.select_for_update().get(id=str(camera_id))
            c_settings, created = CollectorSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                c_settings.camera_fields = settings.REQUIRED_CAMERA_FIELDS
                c_settings.save()

            camera_info = {}
            if camera_data.fields:
                camera_info = {item.name.lower(): item.value or None for item in camera_data.fields}

            if camera_data.agent_id:
                AgentManager.add_cameras(camera_data.agent_id, [camera.id], workspace_id)

            missed_fields = set(camera_info) - set(c_settings.camera_fields)
            if missed_fields:
                raise Exception("One or more camera fields are unavailable")

            ok = CameraManager(camera_id, workspace_id).update_camera_info(info=camera_info)

        return CameraManageOutput(ok=ok, camera=CameraManager(camera_id, workspace_id).get_camera())

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Add cameras to agent")
    def add_cameras_to_agent(self,
                             info: Info,
                             cameras_ids: type_desc(List[ID], "List of cameras ids"),
                             agent_id: type_desc(ID, "Agent id")) -> AgentManageOutput:
        ws_id = get_workspace_id(info)
        agent = AgentManager.add_cameras(agent_id, cameras_ids, ws_id)
        return AgentManageOutput(ok=True, agent=agent)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive], description="Remove cameras from agent")
    def remove_cameras_from_agent(self,
                                  info: Info,
                                  cameras_ids: type_desc(List[ID], "List of cameras ids"),
                                  agent_id: type_desc(ID, "Agent id")) -> AgentManageOutput:
        ws_id = get_workspace_id(info)
        agent = AgentManager.remove_cameras(agent_id, cameras_ids, ws_id)
        return AgentManageOutput(ok=True, agent=agent)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def add_cameras_field(self, info: Info, field_input: ModifyExtraField) -> FieldsModifyResult:
        workspace_id = get_workspace_id(info=info)

        with transaction.atomic():
            c_settings, created = CollectorSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                fields = settings.REQUIRED_CAMERA_FIELDS
            else:
                fields = c_settings.camera_fields

            new_field = field_input.name.lower()
            if not new_field:
                return Exception("Camera field are unavailable")
            elif new_field in fields:
                return Exception("Camera field already exists")

            fields = fields + [new_field]
            c_settings.camera_fields = fields
            c_settings.save()

        return FieldsModifyResult(ok=True, fields=fields)

    @strawberry.mutation(permission_classes=[IsHaveAccess, IsWorkspaceActive])
    def remove_cameras_field(self, info: Info, field_input: ModifyExtraField) -> FieldsModifyResult:
        workspace_id = get_workspace_id(info=info)

        with transaction.atomic():
            c_settings, created = CollectorSettings.objects.get_or_create(workspace_id=workspace_id)
            if created:
                fields = settings.REQUIRED_CAMERA_FIELDS
            else:
                fields = c_settings.camera_fields

            new_field = field_input.name.lower()
            if new_field in settings.REQUIRED_CAMERA_FIELDS:
                return Exception("Camera field is required")

            if new_field not in fields:
                return Exception("Camera field does not exists")

            fields.remove(new_field)
            c_settings.camera_fields = fields

            Camera.objects.filter(workspace_id=workspace_id).update(
                info=Func(
                    F("info") - new_field,
                    function="jsonb"
                )
            )
            c_settings.save()

        return FieldsModifyResult(ok=True, fields=fields)
