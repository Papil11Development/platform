import base64
from enum import Enum

from django.apps import apps

from platform_lib.endpoints.managers.webhookManager import WebhookManager
from user_domain.managers import EmailManager
from label_domain.managers import LabelManager
from collector_domain.managers import CameraManager
from main.settings import BASE_SITE_URL


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
        profile_model = apps.get_model('person_domain', 'Profile')
        blob_model = apps.get_model('data_domain', 'BlobMeta')

        profile = profile_model.objects.get(id=notification_info.get("profile_id"))
        profile_blob_id = profile.info.get('avatar_id')

        presence_context = {
            "notification_url": f"{BASE_SITE_URL}/notifications",
            "blobs": []
        }

        if camera_id := notification_info.get("camera_id"):
            presence_context["camera"] = CameraManager.get_camera_title(camera_id)

        if pg_title := notification_info.get("profile_group_id"):
            profile_group_title, _ = LabelManager.get_label_data(pg_title)
            presence_context["group"] = profile_group_title

        for blob_id, name in (
                (notification_info.get("realtime_face_photo_id"), 'face'),
                (notification_info.get("realtime_body_photo_id"), 'body'),
                (profile_blob_id, 'avatar')
        ):
            try:
                blob_meta = blob_model.objects.get(id=blob_id)
            except Exception:
                continue

            image = base64.b64encode(blob_meta.blob.data.tobytes()).decode()
            presence_context['blobs'].append((image, name))

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
        notification_type = notification_info['type']

        if notification_type == 'presence':
            profile_model = apps.get_model('person_domain', 'Profile')
            profile = profile_model.objects.get(id=notification_info.get("profile_id"))
            profile_group_title, profile_group_info = LabelManager.\
                get_label_data(notification_info.get('profile_group_id'))
            camera_title = CameraManager.get_camera_title(notification_info.get('camera_id'))

            notif_info = {key: value for key, value in notification_info.items() if
                          key not in ['realtime_face_photo_id', 'realtime_body_photo_id']}
            notif_info['avatar_id'] = profile.info.get('avatar_id')
            notif_info.update(
                {
                    'profile_group_title': profile_group_title,
                    'profile_group_color': profile_group_info.get('color'),
                    'camera_title': camera_title
                }
            )
        else:
            notif_info = notification_info

        return notif_info

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
        profile_group_title, profile_group_info = LabelManager.\
            get_label_data(notification_info.get('profile_group_id'))
        camera_title = CameraManager.get_camera_title(notification_info.get('camera_id'))
        notification_info.update(
            {
                'profile_group_title': profile_group_title,
                'profile_group_color': profile_group_info.get('color'),
                'camera_title': camera_title
            }
        )
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
