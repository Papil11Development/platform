from abc import ABC
from celery import shared_task, Task
from typing import List, Dict

from main.settings import PUBLIC_KIBANA_URL
from django.db.transaction import atomic
from user_domain.api.utils import create_space_elk
from user_domain.models import Workspace

from platform_lib.exceptions import KibanaError


class AnalyticsStatus(Task, ABC):
    @staticmethod
    def _get_variable_from_args_or_kwargs(args, kwargs, arg_pos_number: int, arg_name: str):
        return args[arg_pos_number] if len(args) > arg_pos_number else kwargs[arg_name]

    def _manage_connection_status(self, args: List, kwargs: Dict):
        workspace_id = self._get_variable_from_args_or_kwargs(args, kwargs, 3, "workspace_id")
        features = {
            "retail_analytics": {
                "url": "failed",
            },
            "advertising_analytics": {
                "url": "failed",
            }
        }
        with atomic():
            locked_ws = Workspace.objects.select_for_update().get(id=workspace_id)
            locked_ws.config.update({
                'features': features,
            })
            locked_ws.save()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self._manage_connection_status(args, kwargs)


@shared_task(bind=True, autoretry_for=(Exception,),
             retry_kwargs={'max_retries': 3, 'countdown': 10}, base=AnalyticsStatus)
def sign_up_kibana(self, username: str, password: str, workspace_id: str, analytics_type: str):
    workspace = Workspace.objects.get(id=workspace_id)
    feature = workspace.config.get('features', {}).get(analytics_type, {})
    if not feature.get('url') and not feature.get('index'):
        with atomic():
            locked_ws = Workspace.objects.select_for_update().get(id=workspace.id)
            try:
                data = create_space_elk(username, password, str(workspace.id), workspace.title, analytics_type)
            except Exception:
                raise KibanaError(f'Error when creating {analytics_type}.', workspace_id=str(workspace.id))

            url_elk = f'{PUBLIC_KIBANA_URL}/s/{data["space_id"]}/app/dashboards#/view/{data["dashboard"]}'
            features = locked_ws.config.get('features', {})
            features[analytics_type] = {
                'enabled': True,
                'url': url_elk,
                'index': data['index_id'],
            }

            locked_ws.config.update({
                'features': features,
            })
            locked_ws.save()
