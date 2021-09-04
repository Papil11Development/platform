import copy
from abc import ABC
from typing import Optional, List, Dict

from celery import shared_task, Task
from django.db.models import Q
from notifiers.exceptions import NotificationError

from data_domain.managers import OngoingManager
from notification_domain.managers import NotificationLifetimeCycleManager, NotificationManager
from notification_domain.models import Trigger, Notification
from notification_domain.utils import EndpointRouter


@shared_task
def triggers_handler(called_workspace_id: Optional[str] = None):
    packed_ongoings_dict = {}

    def __get_parent_process(sample: dict) -> dict:
        return next(filter(lambda track: track.get('object', {}).get('class') == 'human', sample['processes']), {})

    def ongoings_pack(raw_ongoings_to_pack: List) -> List:
        """
        Group person from ongoings by location, roi, camera_id and e.t.c.
        """

        def calculate_group_key(ongoing: dict) -> str:
            return f'{ongoing.get("camera_id", "")}:{ongoing.get("location_id", "")}'

        ongoing_group = dict()
        raw_ongoings_copied = copy.deepcopy(raw_ongoings_to_pack)

        for ongoing in raw_ongoings_copied:
            key = calculate_group_key(ongoing)
            human = __get_parent_process(ongoing)
            human_object = human['object']

            profile_group_list = human_object.get('match_data', {}).get('profileGroups', [])
            human_object['profile_group_ids'] = [group.get('id') for group in profile_group_list]
            human_object['have_face_best_shot'] = ongoing.get('have_face_best_shot')
            human_object['have_body_best_shot'] = ongoing.get('have_body_best_shot')
            human_object['activity_id'] = human['id']

            if key in ongoing_group:
                ongoing_group[key]['persons'].append(human_object)
            else:
                ongoing_group[key] = {
                    'camera_id': ongoing.get('camera_id', ''),
                    'location_ids': [ongoing.get('location_id', '')],
                    'attention_area_ids': [],
                    'area_type_ids': [],
                    'persons': [human_object]
                }

        return list(ongoing_group.values())

    def get_triggers(workspace_id: Optional[str] = None):
        query_filter = Q(workspace__config__is_active=True)
        if workspace_id:
            query_filter &= Q(workspace__id=workspace_id)
        return Trigger.objects.select_related("workspace").filter(query_filter)

    def get_active_notifications(workspace_id: Optional[str] = None):
        query_filter = Q(is_active=True)
        if workspace_id:
            query_filter &= Q(workspace__id=workspace_id)
        return Notification.objects.select_related("workspace").filter(query_filter)

    def get_packed_ongoings(workspace_id: str):
        """
        Get ongoing from dictionary or get result from cache and save to dict

        Parameters
        ----------
        workspace_id: str
            workspace_id that uses as cache key
        """
        if workspace_id in packed_ongoings_dict.keys():
            return packed_ongoings_dict[workspace_id]
        else:
            raw_ongoings = OngoingManager.get_ongoings(workspace_id=workspace_id)

            if raw_ongoings:
                packed_ongoings = ongoings_pack(raw_ongoings)
            else:
                packed_ongoings = []

            packed_ongoings_dict[workspace_id] = packed_ongoings
            return packed_ongoings

    active_notifications = list(get_active_notifications(called_workspace_id))
    workspace_ids_set = set()
    for trigger in get_triggers(called_workspace_id):
        cached_packed_ongoings = get_packed_ongoings(trigger.workspace.id)

        # lambda for reduce database connection time overhead
        trigger_active_notifications = list(filter(lambda x: x.meta["trigger_id"] == str(trigger.id),
                                                   active_notifications))
        if cached_packed_ongoings or len(trigger_active_notifications):
            workspace_ids_set.add(str(trigger.workspace.id))
            notification_lcm = NotificationLifetimeCycleManager(trigger,
                                                                active_notifications=trigger_active_notifications)
            notification_lcm.handle_notification(cached_packed_ongoings,
                                                 fast_mode=bool(called_workspace_id))


class SendingStatusTask(Task, ABC):
    """
    Base celery task for updating notification sending statuses
    """
    @staticmethod
    def _get_variable_from_args_or_kwargs(args, kwargs, arg_pos_number: int, arg_name: str):
        return args[arg_pos_number] if len(args) > arg_pos_number else kwargs[arg_name]

    def _manage_sending_status(self,
                               sending_status: NotificationManager.SendingStatus,
                               args: List,
                               kwargs: Dict):
        notification_id = self._get_variable_from_args_or_kwargs(args, kwargs, 0, "notification_id")
        workspace_id = self._get_variable_from_args_or_kwargs(args, kwargs, 1, "workspace_id")
        endpoint_id = self._get_variable_from_args_or_kwargs(args, kwargs, 2, "endpoint_id")

        NotificationManager.update_notification_sending_status(workspace_id,
                                                               notification_id,
                                                               endpoint_id,
                                                               sending_status)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        self._manage_sending_status(NotificationManager.SendingStatus.RETRYING, args, kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        self._manage_sending_status(NotificationManager.SendingStatus.SUCCESS, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self._manage_sending_status(NotificationManager.SendingStatus.FAILED, args, kwargs)


# For proper task retry because original NotificationError cause worker to fail
class NotificationException(Exception):
    pass


# notification_id and workspace_id need for saving status in notification meta and using in SendingStatusTask
@shared_task(autoretry_for=(NotificationException,),
             max_retries=5,
             retry_backoff=5,
             retry_backoff_max=700,
             retry_jitter=True,
             base=SendingStatusTask)
def send_notification_task(notification_id: str, workspace_id: str, endpoint_id: str,
                           endpoint_type: str,
                           endpoint_meta: dict,
                           message_data: dict):
    try:
        EndpointRouter.route(endpoint_type, endpoint_meta, message_data)
    except NotificationError as ex:
        raise NotificationException(str(ex))
