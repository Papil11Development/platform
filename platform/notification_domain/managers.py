import logging
import uuid
from datetime import timedelta
from enum import Enum
from typing import Optional, List, Dict, Union, Callable

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import F, QuerySet
from strawberry import ID

from collector_domain.models import Camera
from data_domain.models import Activity
from label_domain.models import Label
from main import celery
from notification_domain.models import Endpoint, Trigger, Notification
from notification_domain.utils import NotificationMessageGenerator
from person_domain.models import Profile
from platform_lib.managers import TriggerMetaManager, ActivityProcessManager
from platform_lib.meta_language_parser import MetaLanguageParser, PresenceResult
from platform_lib.utils import utcnow_with_tz

logger = logging.getLogger(__name__)


class TriggerManager:
    def __init__(self, workspace_id: str, trigger_id: Optional[str] = None):
        self.workspace_id = workspace_id
        self.trigger = None
        if trigger_id is not None:
            self.trigger = Trigger.objects.get(
                workspace_id=self.workspace_id,
                id=trigger_id
            )

    def get_trigger(self) -> Trigger:
        return self.trigger

    @staticmethod
    def delete_trigger(trigger_id: ID):
        with transaction.atomic():
            trigger = Trigger.objects.select_for_update().get(id=trigger_id)
            trigger.endpoints.clear()
            trigger.delete()

    def create_trigger(self, title: str, meta: Dict, endpoint_ids: Optional[str] = None) -> Trigger:
        endpoints = []
        if endpoint_ids:
            endpoints = Endpoint.objects.filter(workspace_id=self.workspace_id, id__in=endpoint_ids)
        with transaction.atomic():
            trigger = Trigger.objects.create(workspace_id=self.workspace_id, title=title, meta=meta)
            trigger.endpoints.add(*endpoints)

        return trigger

    @staticmethod
    def add_endpoint(trigger_id: Union[str, uuid.UUID], endpoint: Endpoint):
        with transaction.atomic():
            trigger = Trigger.objects.select_for_update().get(id=trigger_id)
            trigger.endpoints.add(endpoint)
            trigger.save()

    @staticmethod
    def remove_endpoint(trigger_id: Union[str, uuid.UUID], endpoint: Endpoint):
        with transaction.atomic():
            trigger = Trigger.objects.select_for_update().get(id=trigger_id)
            trigger.endpoints.remove(endpoint)
            trigger.save()

    def update_trigger(self,
                       trigger_id: Union[str, uuid.UUID],
                       title: Optional[str] = None,
                       endpoint: List[Endpoint] = None,
                       notification_params: Optional[Dict] = None):
        with transaction.atomic():
            trigger = Trigger.objects.select_for_update().get(workspace_id=self.workspace_id, id=trigger_id)

            if title is not None:
                trigger.title = title

            if notification_params is not None:
                meta_manager = TriggerMetaManager(trigger.meta)
                meta_manager.update_notification_params(notification_params or {})
                trigger.meta = meta_manager.get_meta()

            if endpoint is not None:
                trigger.endpoints.set(endpoint)

            trigger.save()

            return trigger

    def create_label_trigger(self,
                             targets_list: List,
                             title: Optional[str] = None,
                             endpoints: Optional[List[Endpoint]] = None,
                             notification_params: Optional[Dict] = None):

        if notification_params is None:
            notification_params = {}

        if endpoints is None:
            endpoints = []

        if 'lifetime' not in notification_params:
            notification_params['lifetime'] = settings.NOTIFICATION_DEFAULT_TTL

        with transaction.atomic():
            meta = TriggerMetaManager() \
                .add_presence_variable(targets_list, 0, ">") \
                .update_notification_params(notification_params) \
                .get_meta()
            if not title:
                title = f'Trigger for watchlist {",".join([label.title for label in targets_list])}'
            trigger = Trigger.objects.create(workspace_id=self.workspace_id, title=title, meta=meta)
            trigger.endpoints.set(endpoints)

        return trigger

    # @staticmethod
    # def create_default_triggers(workspace_id: str):
    #     label = apps.get_model('label_domain', 'Label')
    #     trigger_manager = TriggerManager(workspace_id)
    #     vip_label = label.objects.filter(workspace_id=workspace_id,
    #                                      title=settings.DEFAULT_PROFILE_LABEL_TITLES[1]).first()
    #     trigger_manager.create_label_trigger([vip_label])
    #     shoplifter_label = label.objects.filter(workspace_id=workspace_id,
    #                                             title=settings.DEFAULT_PROFILE_LABEL_TITLES[2]).first()
    #     trigger_manager.create_label_trigger([shoplifter_label])


class EndpointManager:
    class DefaultAlias(str, Enum):
        OWNER_EMAIL = "owner_email"
        WEB_INTERFACE = "web_interface"

    def __init__(self, workspace_id: str, endpoint_id: Optional[str] = None):
        self.workspace_id = workspace_id
        self.endpoint = None
        if endpoint_id is not None:
            self.endpoint = Endpoint.objects.get(
                workspace_id=self.workspace_id,
                id=endpoint_id
            )

    def get_by_ids(self, ids: List[Union[str, uuid.UUID]]) -> QuerySet[Endpoint]:
        endpoints = Endpoint.objects.filter(workspace_id=self.workspace_id, id__in=ids)

        # set for proper count validation
        if endpoints.count() != len(set(ids)):
            raise Endpoint.DoesNotExist('Endpoint does not exist')

        return endpoints

    def get_default_by_alias(self, aliases: List[DefaultAlias]) -> QuerySet[Endpoint]:
        endpoints = Endpoint.objects.filter(workspace_id=self.workspace_id,
                                            meta__default_alias__in=map(lambda x: x.value, aliases))

        # set for proper count validation
        if endpoints.count() != len(set(aliases)):
            raise Endpoint.DoesNotExist('Endpoint does not exist')

        return endpoints

    def get_endpoint(self) -> Endpoint:
        return self.endpoint

    def endpoint_exist(self, endpoint_id: Union[str, uuid.UUID]) -> bool:
        return Endpoint.objects.filter(workspace_id=self.workspace_id, id=endpoint_id).exists()

    def delete_endpoint(self, endpoint_ids: List[str]):
        with transaction.atomic():
            endpoints = Endpoint.objects.select_for_update().filter(workspace_id=self.workspace_id, id__in=endpoint_ids)
            for endpoint in endpoints:
                endpoint.triggers.clear()
            endpoints.delete()

    def create_default_endpoints(self, owner_email: str) -> List[Endpoint]:
        owner_meta = {
            "target_email": owner_email
        }

        return [self.__create_endpoint(meta=owner_meta,
                                       e_type=Endpoint.Type.EMAIL,
                                       default_alias=self.DefaultAlias.OWNER_EMAIL),
                self.__create_endpoint(meta={},
                                       e_type=Endpoint.Type.WEB_INTERFACE,
                                       default_alias=self.DefaultAlias.WEB_INTERFACE)
                ]

    def create_email_endpoint(self, target_email: str) -> Endpoint:
        endpoint_meta = {
            "target_email": target_email
        }
        return self.__create_endpoint(meta=endpoint_meta, e_type=Endpoint.Type.EMAIL)

    def create_webhook_endpoint(self, url: str, method: str) -> Endpoint:
        endpoint_meta = {
            "url": url,
            "method": method
        }
        return self.__create_endpoint(meta=endpoint_meta, e_type=Endpoint.Type.WEBHOOK)

    def __create_endpoint(self,
                          meta: Dict,
                          e_type: Optional[str] = None,
                          default_alias: Optional[DefaultAlias] = None) -> Endpoint:
        if default_alias is not None:
            meta.update({'default_alias': default_alias.value})
        endpoint = Endpoint.objects.create(workspace_id=self.workspace_id, meta=meta, type=e_type)
        return endpoint


class NotificationManager:
    class SendingStatus(str, Enum):
        PENDING = "pending"
        SUCCESS = "success"
        FAILED = "failed"
        RETRYING = "retrying"

    class MetaGenerator:
        def __init__(self,
                     type_: str,
                     trigger_id: str,
                     camera: Camera):
            self.notification_meta = {
                "type": type_,
                "trigger": {"id": trigger_id},
                "camera": {"id": str(camera.id), **camera.info},
            }

        def add_profile_info(self, profile_id: str, profile_info: dict):
            self.notification_meta["profile"] = {
                "id": profile_id,
                **profile_info
            }
            return self

        def add_matched_profile_group_info(self, group_id: str, group_title: str, group_info: dict):
            # TODO probably there is a better variant
            groups = self.notification_meta.get("matched_profile_groups", [])

            groups.append(
                {
                    "id": group_id,
                    "title": group_title,
                    **group_info
                }
            )

            self.notification_meta["matched_profile_groups"] = groups
            return self

        def add_activity_info(self, activity_id: str, face_photo_id: str, body_photo_id: str, date: str):
            self.notification_meta["activity"] = {
                "id": activity_id,
                "face_photo_id": face_photo_id,
                "body_photo_id": body_photo_id,
                "detection_date": date
            }
            return self

        # def enrich_limit_info(self, limit: int):
        #     self.notification_meta["limit"] = limit
        #     return self

        # def enrich_current_count_info(self, current_count: int):
        #     self.notification_meta["current_count"] = current_count
        #     return self

        # def enrich_lifetime_info(self, lifetime: int):
        #     self.notification_meta["lifetime"] = lifetime
        #     return self

        # def enrich_realtime_face_photo_id(self, realtime_face_photo_id: str):
        #     self.notification_meta["realtime_face_photo_id"] = realtime_face_photo_id
        #     return self
        #
        # def enrich_realtime_body_photo_id(self, realtime_body_photo_id: str):
        #     self.notification_meta["realtime_body_photo_id"] = realtime_body_photo_id
        #     return self

        def get_meta_dict(self):
            return self.notification_meta

        @classmethod
        def generate_presence_meta(cls,
                                   trigger_id: str,
                                   camera: Camera,
                                   profile: Profile,
                                   profile_groups: List[Label],
                                   activity: Activity) -> dict:
            notification_meta = cls("presence", trigger_id, camera=camera)

            activity_manager = ActivityProcessManager(activity_data=activity.data)
            face_best_shot = (activity_manager.get_face_best_shot() or {}).get('id')
            body_best_shot = (activity_manager.get_body_best_shot() or {}).get('id')

            (notification_meta
             .add_profile_info(str(profile.id), profile.info)
             .add_activity_info(str(activity.id),
                                face_best_shot,
                                body_best_shot,
                                activity_manager.get_human_timeinterval()[0]))

            for profile_group in profile_groups:
                notification_meta.add_matched_profile_group_info(str(profile_group.id),
                                                                 profile_group.title,
                                                                 profile_group.info)

            return notification_meta.get_meta_dict()

        # @classmethod
        # def generate_location_overflow_meta(cls,
        #                                     trigger_id: str,
        #                                     location_id: str,
        #                                     limit: int,
        #                                     current_count: int,
        #                                     lifetime: int) -> dict:
        #     return cls("location_overflow", trigger_id, location_id) \
        #         .enrich_limit_info(limit) \
        #         .enrich_lifetime_info(lifetime) \
        #         .enrich_current_count_info(current_count) \
        #         .get_meta_dict()

    class Presence:
        @staticmethod
        def deactivate(notification_list: List[Notification], lifetime: int):
            with transaction.atomic():
                date_from = utcnow_with_tz() - timedelta(seconds=lifetime)
                notifications = Notification.objects.select_for_update().filter(
                    id__in=[notification.id for notification in notification_list],
                    last_modified__lt=date_from)

                notifications.update(is_active=False)

        @staticmethod
        def deprecate_with_lifetime(trigger_id: str, lifetime: int):
            with transaction.atomic():
                date_from = utcnow_with_tz() - timedelta(seconds=lifetime)
                notifications = Notification.objects.select_for_update().filter(meta__trigger__id=trigger_id,
                                                                                is_active=True,
                                                                                last_modified__lt=date_from)
                notifications.update(is_active=False)

    # def create_location_overflow_notification(self,
    #                                           location_id: str,
    #                                           limit: int,
    #                                           lifetime: int,
    #                                           current_count: int,
    #                                           trigger: Trigger) -> Notification:
    #
    #     return Notification.objects.create(workspace=trigger.workspace,
    #                                        meta=self.MetaGenerator.generate_location_overflow_meta(
    #                                            trigger_id=str(trigger.id),
    #                                            location_id=location_id,
    #                                            limit=limit,
    #                                            lifetime=lifetime,
    #                                            current_count=current_count),
    #                                        is_active=False)

    def __init__(self, workspace_id: str, notification_id: Optional[str] = None):
        self.workspace_id = workspace_id
        self.notification = None
        if notification_id is not None:
            self.notification = Notification.objects.get(
                workspace_id=self.workspace_id,
                id=notification_id
            )
        self.time_inaccuracy = 0.2
        self.addition_reactivate_task_period = 5

    @staticmethod
    def create_notification(trigger: Trigger,
                            meta: Dict) -> Notification:
        return Notification.objects.create(
            workspace=trigger.workspace,
            meta=meta,
            is_active=True
        )

    def get_notification(self) -> Notification:
        return self.notification

    @classmethod
    def update_notification_sending_status(cls,
                                           workspace_id: Union[str, uuid.UUID],
                                           notification_id: Union[str, uuid.UUID],
                                           endpoint_id: str,
                                           sending_status: SendingStatus):
        """
        Update notification sending status in meta

        Parameters
        ----------
        workspace_id: Union[str, uuid.UUID]
            Notification workspace id
        notification_id: Union[str, uuid.UUID]
            Notification id
        endpoint_id: str
            Endpoint id
        sending_status: SendingStatus
            Status to be updated to
        """
        with transaction.atomic():
            notification = Notification.objects.select_for_update().get(workspace_id=workspace_id,
                                                                        id=notification_id)

            updated_statuses = notification.meta.get("statuses", {})
            updated_statuses[endpoint_id] = sending_status.value

            notification.meta.update({"statuses": updated_statuses})

            notification.save()

    @staticmethod
    def is_exist(trigger_id: str) -> bool:
        return Notification.objects.filter(is_active=True, meta__trigger__id=trigger_id).exists()

    @staticmethod
    def get_active(trigger_id: str) -> QuerySet[Notification]:
        return Notification.objects.filter(meta__trigger__id=trigger_id, is_active=True)

    @staticmethod
    def get_active_by_profile_id(trigger_id: str, profile_id: str) -> QuerySet[Notification]:
        return Notification.objects.filter(meta__trigger__id=trigger_id,
                                           meta__profile__id=profile_id,
                                           is_active=True).all()

    def delete(self, notification_ids: List[str]):
        with transaction.atomic():
            notifications = Notification.objects.select_for_update().filter(workspace_id=self.workspace_id,
                                                                            id__in=notification_ids)
            notifications.delete()

    def deactivate(self, notification_ids: str):
        with transaction.atomic():
            notification = Notification.objects.select_for_update().filter(workspace_id=self.workspace_id,
                                                                           id=notification_ids)
            notification.update(is_active=False)

    @staticmethod
    def deactivate_query_set(notifications: QuerySet):
        notifications.update(is_active=False)

    @staticmethod
    def deactivate_object_list(notification_list: List[Notification]):
        with transaction.atomic():
            notifications = Notification.objects.select_for_update().filter(
                id__in=[notification.id for notification in notification_list])
            notifications.update(is_active=False)

    def activate(self, notification_ids: str):
        with transaction.atomic():
            notification = Notification.objects.select_for_update().filter(workspace_id=self.workspace_id,
                                                                           id=notification_ids)
            notification.update(is_active=True)

    def view(self, notification_ids: List[str]):
        with transaction.atomic():
            notifications = Notification.objects.select_for_update().filter(workspace_id=self.workspace_id,
                                                                            id__in=notification_ids)
            notifications.update(is_viewed=True)
            for notification in notifications.all():
                notification.save()

    def view_all(self):
        with transaction.atomic():
            notifications = Notification.objects.select_for_update().filter(workspace_id=self.workspace_id)
            notifications.update(is_viewed=True)

    def create(self, meta: dict, is_active: Optional[bool] = True) -> Notification:
        with transaction.atomic():
            notification = Notification.objects.create(workspace_id=self.workspace_id, meta=meta, is_active=is_active)
        return notification

    def get_reactivatable(self, trigger: Trigger) -> QuerySet[Notification]:
        lifetime = TriggerMetaManager(trigger.meta).get_trigger_lifetime() or settings.NOTIFICATION_DEFAULT_TTL
        top_time_bound = utcnow_with_tz() - timedelta(seconds=lifetime)
        low_time_bound = top_time_bound - timedelta(seconds=self.addition_reactivate_task_period)
        return Notification.objects.filter(
            meta__trigger__id=str(trigger.id), is_active=False,
            last_modified__gte=F('creation_date') - timedelta(seconds=self.time_inaccuracy),
            last_modified__lte=F('creation_date') + timedelta(seconds=self.time_inaccuracy),
            creation_date__gt=low_time_bound,
            creation_date__lte=top_time_bound + timedelta(seconds=self.time_inaccuracy)) \
            .order_by('-last_modified').all()

    @staticmethod
    def refresh_last_modified(notification_id: str):
        with transaction.atomic():
            notification = Notification.objects.select_for_update().get(id=notification_id)
            notification.last_modified = utcnow_with_tz()
            notification.save()

    @staticmethod
    def refresh_last_modified_query_set(notifications: QuerySet):
        notifications.update(last_modified=utcnow_with_tz())

    @staticmethod
    def refresh_last_modified_object_list(notification_list: List[Notification]):
        with transaction.atomic():
            notifications = Notification.objects.select_for_update().filter(id__in=[notification.id for
                                                                                    notification in notification_list])
            notifications.update(last_modified=utcnow_with_tz())

    @staticmethod
    def update_persons_count(notification_id: str, meta: dict):
        with transaction.atomic():
            notification = Notification.objects.select_for_update().get(id=notification_id)
            notification.meta.update(meta)
            notification.save()

    def delete_not_used(self, trigger_id: str):
        with transaction.atomic():
            for not_used_notification in Notification.objects.filter(
                    meta__trigger__id=trigger_id,
                    is_active=False,
                    last_modified__gte=F('creation_date') - timedelta(seconds=self.time_inaccuracy),
                    last_modified__lte=F('creation_date') + timedelta(seconds=self.time_inaccuracy)
            ).all():
                not_used_notification.delete()

    @staticmethod
    def deprecate_no_lifetime(trigger_id: str):
        Notification.objects.filter(meta__trigger__id=trigger_id,
                                    is_active=True).update(is_active=False)

    @staticmethod
    def deprecate_with_lifetime(trigger_id: str, lifetime: int):
        date_from = utcnow_with_tz() - timedelta(seconds=lifetime)
        Notification.objects.filter(meta__trigger__id=trigger_id,
                                    is_active=True,
                                    last_modified__lt=date_from).update(is_active=False)

    def potential_use_exist(self, trigger_id: str, lifetime: int) -> bool:
        time_bound = utcnow_with_tz() - timedelta(seconds=lifetime) - \
                     timedelta(seconds=self.addition_reactivate_task_period)

        return Notification.objects.filter(
            meta__trigger__id=trigger_id, is_active=False,
            last_modified__gte=F('creation_date') - timedelta(seconds=self.time_inaccuracy),
            last_modified__lte=F('creation_date') + timedelta(seconds=self.time_inaccuracy),
            creation_date__gt=time_bound) \
            .exists()


class NotificationLifetimeCycleManager:
    """
    Class that helps to handle and route trigger notifications

    Parameters
    ----------
    trigger: Trigger
        Trigger to handle its notifications
    """

    # label_model = apps.get_model('label_domain', 'Label')
    camera_model = apps.get_model('collector_domain', 'Camera')
    activity_model = apps.get_model('data_domain', 'Activity')

    def get_notification_function(self, notification_type: str, fast_mode: bool) -> Optional[Callable]:
        mapping_name = f'{notification_type}{"_fast" if fast_mode else ""}'

        scheme_mapping = {
            'presence': self.presence_scheme_reactivate,
            # 'location_overflow': self.location_overflow_schema,
            'presence_fast': self.presence_scheme_only_creation
        }

        try:
            function = scheme_mapping[mapping_name]
        except KeyError:
            function = None

        return function

    def __init__(self, trigger: Trigger, active_notifications: List[Notification] = None):
        self.workspace_id = str(trigger.workspace.id)
        self.manager = NotificationManager(workspace_id=self.workspace_id)
        self.trigger = trigger
        self.meta_language_parser = MetaLanguageParser(TriggerMetaManager(trigger.meta).get_condition_language())

        if active_notifications is None:
            self.active_notifications = list(self.manager.get_active(str(self.trigger.id)))
        else:
            self.active_notifications = active_notifications

    @staticmethod
    def send_notification_to_endpoints(workspace_id: str,
                                       notification_id: str,
                                       notification_info: dict,
                                       trigger: Trigger):
        send_notification_task = celery.app.signature('notification_domain.tasks.send_notification_task')

        for endpoint in trigger.endpoints.all():
            message_data = NotificationMessageGenerator.get_message_data(endpoint.get_type_display(),
                                                                         notification_info)

            send_notification_task.delay(notification_id,
                                         workspace_id,
                                         endpoint_id=str(endpoint.id),
                                         endpoint_type=endpoint.get_type_display(),
                                         endpoint_meta=endpoint.meta,
                                         message_data=message_data)

    # ------------- websockets disabled ----------------

    # def send_notification_in_websocket(self, notification: Notification):
    #     profile_model = apps.get_model('person_domain', 'Profile')
    #
    #     profile_info = profile_model.objects.get(id=notification.meta.get('profile_id')).info
    #
    #     # enrich notification_meta_with time
    #     notif_socket_meta = copy.deepcopy(notification.meta)
    #     notif_socket_meta['id'] = str(notification.id)
    #     # TODO: Make nested data of profile object (avatar_id, name and etc)
    #     notif_socket_meta['name'] = profile_info.get('name')
    #     notif_socket_meta['avatar_id'] = profile_info.get('avatar_id')
    #     notif_socket_meta['creation_date'] = notification.creation_date.isoformat()
    #     notif_socket_meta['last_modified'] = notification.last_modified.isoformat()
    #
    #     # send notification only if endpoint web_interface is linked to trigger
    #     if self.trigger.endpoints.filter(type=Endpoint.Type.WEB_INTERFACE).exists():
    #         send_websocket_notifications(self.workspace_id, notif_socket_meta)

    def handle_notification(self, packed_ongoings, fast_mode: bool = False):
        """
        Use ongoings and trigger meta to calculate current state info and raise notification based on this state.
        """

        result, result_values = self.meta_language_parser.calculate_meta_condition(
            packed_ongoings,
            self.trigger.workspace.config.get('notification_score_threshold', settings.DEFAULT_SCORE_THRESHOLD_VALUE)
        )
        result_value = list(result_values.values())[0]

        variable_type = self.meta_language_parser.get_variable_type_by_number(0)
        notification_func = self.get_notification_function(notification_type=variable_type, fast_mode=fast_mode)

        if not self.meta_language_parser.get_condition() and notification_func is not None:
            notification_func(result, result_value)

    def __create_presence_meta(self, target: dict) -> Dict:
        profile_id = target['profile_id']
        camera_id = target['camera_id']
        activity_id = target['activity_id']

        activity = (self.activity_model.objects.filter(id=activity_id)
                    .select_related('camera')
                    .select_related('person')
                    .select_related('person__profile')
                    .prefetch_related('person__profile__profile_groups'))[0]

        if activity.person is None:
            raise Exception('Activity with match data but without person')

        if activity.person.profile is None:
            raise Exception('Activity with match data but without profile')

        profile = activity.person.profile
        camera = activity.camera

        profile_groups = activity.person.profile._prefetched_objects_cache[
            activity.person.profile.profile_groups.prefetch_cache_name
        ]
        profile_group_mapping = {str(group.id): group for group in profile_groups}
        profile_group_ids = self.meta_language_parser.get_profile_group_ids_from_variable(0)

        intersected_ids = set(profile_group_ids).intersection(set(profile_group_mapping.keys()))

        # TODO made specific notification Exception
        if len(intersected_ids) == 0:
            raise Exception(
                f'''Wrong profile groups. Profile not in group that selected in trigger
                Trigger profile groups: {profile_group_ids}
                Profile groups: {profile_group_mapping.keys()}
            ''')
        if profile_id != str(profile.id):
            raise Exception(f'''Wrong profile id. Ongoing profile id not matched with linked to activity profile
                Ongoing profile id: {profile_id}
                Activity profile id: {profile.id}
            ''')
        if camera_id != str(camera.id):
            raise Exception(f'''Wrong camera id. Ongoing camera id not matched with linked to activity camera
                Ongoing camera id: {camera_id}
                Activity camera id: {camera.id}
            ''')

        return self.manager.MetaGenerator.generate_presence_meta(
            trigger_id=str(self.trigger.id),
            camera=camera,
            activity=activity,
            profile=profile,
            profile_groups=[
                profile_group[1] for profile_group in profile_group_mapping.items()
                if profile_group[0] in intersected_ids
            ]
        )

    def __create_notification(self, notification_meta: dict) -> Notification:
        notification = self.manager.create_notification(self.trigger, notification_meta)

        self.send_notification_to_endpoints(
            self.workspace_id,
            str(notification.id),
            notification.meta,
            self.trigger
        )

        # ------------- websockets disabled ----------------

        # self.send_notification_in_websocket(notification)

        # update active notifications list
        self.active_notifications.append(notification)

        return notification

    def presence_scheme_only_creation(self, result: bool, result_value: PresenceResult):
        if result:
            targets = result_value.target_info

            for target in targets:
                person_notification = next(
                    filter(lambda x:
                           x.meta['profile']['id'] == target['profile_id']
                           and
                           x.meta['camera']['id'] == target['camera_id'],
                           self.active_notifications), None
                )

                if not person_notification:
                    self.__create_notification(self.__create_presence_meta(target))

    def presence_scheme_reactivate(self, result: bool, result_value: PresenceResult):
        """
        Lifetime cycle schema for presence notification

        Parameters
        ----------
        result: bool
            Result of condition calculation by meta parser
        result_value: PresenceResult
            Information gather while condition calculation that need for notification info
        """
        lifetime = TriggerMetaManager(self.trigger.meta).get_trigger_lifetime() or settings.NOTIFICATION_DEFAULT_TTL

        def get_notifications_by_targets(targets: list) -> List[Notification]:
            target_notifications = []
            for target in targets:
                person_notification = next(
                    filter(lambda x: x.meta['profile']['id'] == target['profile_id'], self.active_notifications), None
                )
                if person_notification:
                    target_notifications.append(person_notification)

            return target_notifications

        if result:
            # update last modified only on active notifications
            self.manager.refresh_last_modified_object_list(get_notifications_by_targets(result_value.target_info))

        # deprecate only old notifications that modified earlier than lifetime from now
        self.manager.Presence.deprecate_with_lifetime(str(self.trigger.id), lifetime)

# def __create_location_overflow_notification(self, current_count: int, lifetime: int) -> Notification:
#     location_id = self.meta_language_parser.get_places(0)[0].get('uuid')
#     # location_title = self.get_label_title(location_id) if location_id else ''
#     limit = self.meta_language_parser.get_variable_kwargs_by_number(0).get('target_limit')
#
#     return self.manager.create_location_overflow_notification(location_id,
#                                                               limit,
#                                                               lifetime,
#                                                               current_count,
#                                                               self.trigger)

# def location_overflow_schema(self, result: bool, result_value: LocationResult):
#     """
#     Lifetime cycle schema for location_overflow notification
#
#     Parameters
#     ----------
#     result: bool
#         Result of condition calculation by meta parser
#     result_value: LocationResult
#         Information gather while condition calculation that need for notification info
#     """
#
#     lifetime = TriggerMetaManager(self.trigger.meta).get_trigger_lifetime() or 0
#
#     def update_active(persons_count):
#         # Update active notifications
#         for notification in self.manager.get_active(str(self.trigger.id)).all():
#             self.manager.refresh_last_modified(str(notification.id))
#             self.manager.update_persons_count(str(notification.id), meta={'current_count': persons_count})
#
#     def delete_and_deprecate():
#         # Delete not used potential activations and deprecate old notifications
#         self.manager.delete_not_used(str(self.trigger.id))
#         self.manager.deprecate_with_lifetime(str(self.trigger.id), lifetime)
#
#     def activate_potential() -> Notification:
#         # Activate potential notification
#         for activated_notification in self.manager.get_reactivatable(self.trigger):
#             self.manager.activate(activated_notification.id)
#             return activated_notification
#
#     current_count = result_value.current_count
#
#     if result:
#         notification_exist = self.manager.is_exist(str(self.trigger.id))
#         if not notification_exist:
#             # Create new notification if potential use notification not exist
#             if not self.manager.potential_use_exist(str(self.trigger.id), lifetime):
#                 self.__create_location_overflow_notification(current_count, lifetime)
#
#             # TODO remove to activate_potential() when location overflow notification will be updated
#             if (notification := activate_potential()) is not None:
#                 self.send_notification_to_endpoints(self.workspace_id,
#                                                     str(notification.id),
#                                                     notification.meta,
#                                                     self.trigger)
#
#         else:
#             update_active(current_count)
#     else:
#         delete_and_deprecate()
