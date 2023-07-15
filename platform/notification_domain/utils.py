import base64
import copy
import logging
from enum import Enum
from typing import Optional, Union

from django.apps import apps

from collector_domain.managers import CameraManager
from label_domain.managers import LabelManager
from main.settings import BASE_SITE_URL
from platform_lib.endpoints.managers.webhookManager import WebhookManager
from platform_lib.utils import SampleObjectsName
from user_domain.managers import EmailManager

logger = logging.getLogger(__name__)


# Duplicate because of circular import
class EndpointType(str, Enum):
    WEB_INTERFACE = 'Web interface'
    EMAIL = 'Email'
    WEBHOOK = 'Webhook'
    BOT = 'Bot'


class NotificationMessageGenerator:
    @classmethod
    def get_message_generator_mapping(cls):
        return {
            EndpointType.EMAIL.value: cls.email_message_generator,
            EndpointType.WEBHOOK.value: cls.webhook_data_generator,
            EndpointType.WEB_INTERFACE.value: cls.web_interface_data_generator
        }

    @staticmethod
    def __get_presence_context(notification_info: dict):
        blob_model = apps.get_model('data_domain', 'BlobMeta')
        sample_model = apps.get_model('data_domain', 'Sample')

        log_wrong_notification = False

        presence_context = {
            "notification_url": f"{BASE_SITE_URL}/notifications",
            "blobs": []
        }

        avatar_id = None
        try:
            sample_avatar_id = notification_info['profile']['avatar_id']
            sample = sample_model.objects.get(id=sample_avatar_id)
            avatar_id = sample.meta[f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'][0]['$cropImage']['id']
        except KeyError:
            logger.error('No avatar in notification')
            log_wrong_notification = True
        except sample_model.DoesNotExist:
            logger.error(f'No sample for avatar {avatar_id}')
            log_wrong_notification = True
        except Exception:
            logger.error(f'No avatar in sample {sample_avatar_id}', exc_info=True)
            log_wrong_notification = True

        try:
            face_photo_id = notification_info['activity']['face_photo_id']
        except KeyError:
            logger.error('No face photo in notification')
            log_wrong_notification = True
            face_photo_id = None

        try:
            body_photo_id = notification_info['activity']['body_photo_id']
        except KeyError:
            logger.error('No body photo in notification')
            log_wrong_notification = True
            body_photo_id = None

        try:
            camera_id = notification_info['camera']['id']
            presence_context["camera"] = CameraManager.get_camera_title(camera_id)
        except KeyError:
            logger.error('No camera id in notification')
            log_wrong_notification = True

        try:
            profile_groups_data = notification_info['matched_profile_groups']
            presence_context["group"] = LabelManager.get_label_data(profile_groups_data[0].get('id'))[0]
        except KeyError:
            logger.error('No matchend profile groups in notification')
            log_wrong_notification = True

        for blob_id, name in (
                (face_photo_id, 'face'),
                (body_photo_id, 'body'),
                (avatar_id, 'avatar')
        ):
            if not blob_id:
                continue

            try:
                blob_meta = blob_model.objects.get(id=blob_id)
            except Exception as exc:
                log_wrong_notification = True
                logger.error(exc, exc_info=True)
                continue

            image = base64.b64encode(blob_meta.blob.data.tobytes()).decode()
            presence_context['blobs'].append((image, name))

        if log_wrong_notification:
            logger.error(f'Wrong notification {notification_info}')

        return presence_context

    @classmethod
    def webhook_data_generator(cls, notification_info: dict) -> dict:
        """
        Generate from result value message data for webhook endpoint

        Parameters
        ----------
        notification_info: dict
            Notification info witch will be used for generate message

        Returns
        -------
        dict:
            Message data with information about trigger event
        """
        key_words = ['avatar_id', 'face_photo_id', 'body_photo_id']
        mapping = {
            'avatar_id': 'sample_link',
            'main_sample_id': 'main_sample_link',
            'face_photo_id': 'face_photo_link',
            'body_photo_id': 'body_photo_link',
            'realtime_photo': 'realtime_photo_link'
        }
        new_info = copy.deepcopy(notification_info)

        def recursion(element: Optional[Union[dict, list]]):

            if isinstance(element, dict):
                new_fields = {}

                for key, value in element.items():
                    if key in key_words:
                        new_fields[mapping.get(key, key)] = f'{BASE_SITE_URL}/get-image/{value}'\
                            if value is not None else value
                    else:
                        recursion(value)

                element.update(new_fields)

            elif isinstance(element, list):
                for value in element:
                    recursion(value)

        recursion(new_info)

        return new_info

    @classmethod
    def email_message_generator(cls, notification_info: dict) -> dict:
        """
        Generate from result value message data for email endpoint

        Message data structure:
            {
                | "email_from": "email from which the letter will be sent"
                | "subject": "subject of message"
                | "html_message": "text of message in html format"
            }

        Parameters
        ----------
        notification_info: dict
            Notification info witch will be used for generate message

        Returns
        -------
        dict
            Message data with information about trigger event.
        """

        notification_type = notification_info['type']

        if notification_type == 'presence':
            email_key = EmailManager.NOTIFICATION_PRESENCE
            context = cls.__get_presence_context(notification_info)

        elif notification_type == 'location_overflow':
            email_key = EmailManager.NOTIFICATION_OVERFLOW
            context = notification_info

        message_data = {
            "email_key": email_key,
            "context": context
        }

        return message_data

    @classmethod
    def get_message_data(cls, endpoint_type: str, notification_info: dict) -> dict:
        """
        Form message data based on endpoint and result of trigger condition calculation

        Parameters
        ----------
        endpoint_type: str
            Type for which endpoint message will be generated
        notification_info: dict
            Information in notification witch need to be sended
        """
        return cls.get_message_generator_mapping()[endpoint_type](notification_info)

    @classmethod
    def web_interface_data_generator(cls, notification_info: dict) -> dict:
        # profile_group_title, profile_group_info = LabelManager.\
        #     get_label_data(notification_info.get('profile_group_id'))
        # camera_title = CameraManager.get_camera_title(notification_info.get('camera_id'))
        # notification_info.update(
        #     {
        #         'profile_group_title': profile_group_title,
        #         'profile_group_color': profile_group_info.get('color'),
        #         'camera_title': camera_title
        #     }
        # )
        return notification_info


class EndpointRouter:
    """
    Endpoint notification router

    Route notification to physical endpoints by endpoint type
    """

    @classmethod
    def get_route_map(cls):
        return {
            EndpointType.EMAIL.value: cls.send_email,
            EndpointType.WEBHOOK.value: cls.send_webhook,
            EndpointType.WEB_INTERFACE: cls.send_web
        }

    @classmethod
    def route(cls, endpoint_type: str, endpoint_meta: dict, message_data: dict):
        cls.get_route_map()[endpoint_type](endpoint_meta, message_data)

    @staticmethod
    def send_email(endpoint_meta: dict, message_data: dict):
        target_email = endpoint_meta.get('target_email')
        email_key = message_data.get("email_key")
        context = message_data.get("context")
        EmailManager.send_email(email_key=email_key, email=target_email, context=context)

    @staticmethod
    def send_webhook(endpoint_meta: dict, message_data: dict):
        url = endpoint_meta.get('url')
        method = endpoint_meta.get('method')

        WebhookManager.send_message(url, method, request_data=message_data)

    @staticmethod
    def send_web(endpoint_meta: dict, message_data: dict):
        pass
