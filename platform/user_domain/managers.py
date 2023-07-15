import base64
import threading
from typing import List, Optional
from datetime import datetime
import requests
from celery import execute
from email.mime.image import MIMEImage
from django.db import transaction
from django.contrib.auth import login as auth_login, authenticate
from django.contrib.auth.models import Group, AnonymousUser, User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template import Template, Context
from django.core.validators import validate_email
from django.utils import timezone

from django.utils.http import urlencode
from platform_lib.exceptions import InvalidJsonRequest
from user_domain.models import Workspace, Access, EmailTemplate

from platform_lib.utils import ApiError, UsageAnalytics
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import workspace_config_scheme
from main import settings
from user_domain.licensing_api import LicensingOperation


class LoginManager:
    @staticmethod
    def __check_confirmation_token(user: User, token: str):
        if not default_token_generator.check_token(user, token):
            raise ApiError(message='Wrong token', error_code=ApiError.WRONG_TOKEN)

    @staticmethod
    def __check_match_passwords(password: str, confirm_password: str):
        if password != confirm_password:
            raise ApiError(message="Passwords don't match", error_code=ApiError.PASSWORDS_DO_NOT_MATCH)

    @classmethod
    def auth(cls, username: str, password: str, request,
             confirmation_token: str = None, workspace_id: Optional[str] = None) -> Optional[User]:

        if password:
            user = authenticate(request=request, username=username, password=password)
        elif confirmation_token:
            user = cls.__get_user_by_confirmation_token(username, confirmation_token, workspace_id)
        else:
            raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)

        if user is None:
            raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)

        if not user.is_active:
            raise ApiError(message='User is inactive', error_code=ApiError.INACTIVE_USER)

        auth_login(request, user)

        UsageAnalytics(
            operation='login',
            username=user.username,
        ).start()

        return user

    @classmethod
    def __get_user_by_confirmation_token(cls, login, confirmation_token, workspace_id):
        def validation_request_v2():
            get_args = urlencode({"login": login, "token": confirmation_token})
            return requests.session().get(
                f'{settings.LICENSE_SERVER_URL}/api/{settings.LICENSING_PRODUCT_NAME}/validate/?{get_args}')

        if workspace_id is None:
            response = validation_request_v2()
        else:
            try:
                Workspace.objects.get(id=workspace_id)
            except Workspace.DoesNotExist:
                raise ApiError(message='Workspace was not found', error_code=ApiError.WORKSPACE_NOT_FOUND)

            response = validation_request_v2()

        if response.status_code != 200 or not response.json().get('ok'):
            raise ApiError(message='Authorization error', error_code=ApiError.NOT_AUTHORIZED)

        user = User.objects.get(username=login)
        user.backend = 'api_gateway.auth_backends.LicenseServerAuth' if not user.has_usable_password() \
            else 'django.contrib.auth.backends.AllowAllUsersModelBackend'
        return user

    @classmethod
    def registration(cls,
                     email: str,
                     password: str,
                     confirm_password: str,
                     first_name: Optional[str] = None,
                     last_name: Optional[str] = None) -> User:

        if User.objects.filter(username=email).exists():
            raise ApiError(message='User with this email already exists', error_code=ApiError.USER_EXISTS)

        from notification_domain.managers import EndpointManager, TriggerManager   # noqa
        from label_domain.managers import LabelManager  # noqa

        cls.__check_match_passwords(password, confirm_password)
        validate_password(password=password)
        validate_email(email)

        with transaction.atomic():
            user = User.objects.create_user(username=email,
                                            email=email,
                                            password=password,
                                            first_name=first_name if first_name else '',
                                            last_name=last_name if last_name else '',
                                            is_active=False)
            LicensingOperation.create_billing_account(email)
            standalone_group = Group.objects.get(name=settings.STANDALONE_GROUP)
            locked_user = User.objects.select_for_update().get(id=user.id)
            locked_user.groups.add(standalone_group)
            locked_user.save()

        # TODO Move this transaction to user confirmation action
        with transaction.atomic():
            LicensingOperation.create_image_api_license(email)
            workspace = WorkspaceManager.create_workspace(title="Workspace #1", username=email,
                                                          password=password,
                                                          analytics_types=["retail_analytics", "advertising_analytics"])
            LicensingOperation.create_workspace_license((str(workspace.id)), email)
            AccessManager.create_access(user=locked_user, workspace=workspace, permissions=Access.OWNER)
            default_endpoints = EndpointManager(workspace_id=workspace.id).\
                create_default_endpoints(owner_email=user.email)
            default_label = LabelManager.create_default_labels(str(workspace.id), label_titles=['My persons'])

            trigger_manager = TriggerManager(workspace_id=str(workspace.id))
            trigger_manager.create_label_trigger(
                targets_list=default_label,
                endpoints=[default_endpoints[1]]
            )
            EmailManager.send_email(user=user, email_key=EmailManager.CONFIRM_EMAIL)

        return user

    @classmethod
    def change_password(cls, user_id: str, old_password: str, new_password: str, confirm_new_password: str) -> User:
        locked_user = User.objects.select_for_update().get(id=user_id)
        if not locked_user.check_password(old_password):
            raise ApiError(message='Invalid password', error_code=ApiError.INVALID_PASSWORD)

        cls.__check_match_passwords(new_password, confirm_new_password)
        validate_password(password=new_password)

        locked_user.set_password(new_password)
        locked_user.save()

        return locked_user

    @classmethod
    def reset_password(cls, user_id: str, confirmation_token: str, new_password: str,
                       confirm_new_password: str) -> User:
        locked_user = User.objects.select_for_update().get(id=user_id)

        cls.__check_confirmation_token(locked_user, confirmation_token)
        cls.__check_match_passwords(new_password, confirm_new_password)

        locked_user.set_password(new_password)
        locked_user.save()

        return locked_user

    @classmethod
    def confirm_registration(cls, user_id: str, confirmation_token: str):
        locked_user = User.objects.select_for_update().get(id=user_id)
        cls.__check_confirmation_token(locked_user, confirmation_token)
        if not locked_user.is_active:
            locked_user.is_active = True
            locked_user.last_login = timezone.now()
            locked_user.save()

    @classmethod
    def registration_qa_account(cls,
                                email: str,
                                password: str,
                                customer_id: str,
                                with_test_clock: bool = False) -> User:

        if User.objects.filter(username=email).exists():
            raise ApiError(message='User with this email already exists', error_code=ApiError.USER_EXISTS)

        validate_email(email)

        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password)
            group_names = [settings.STANDALONE_GROUP, settings.QA_GROUP]

            if with_test_clock:
                Group.objects.get_or_create(name=settings.TS_GROUP)
                group_names.append(settings.TS_GROUP)

            groups = Group.objects.filter(name__in=group_names).values_list("id", flat=True)
            LicensingOperation.create_billing_account(username=email, customer_id=customer_id)
            locked_user = User.objects.select_for_update().get(id=user.id)
            locked_user.groups.set(groups)
            locked_user.save()

        with transaction.atomic():
            workspace = WorkspaceManager.create_qa_workspace(title="Workspace #1",
                                                             username=email,
                                                             password=password,
                                                             analytics_types=["retail_analytics",
                                                                              "advertising_analytics"])

            AccessManager.create_access(user=locked_user, workspace=workspace, permissions=Access.OWNER)
            LicensingOperation.create_workspace_license(workspace.id, email)
            LicensingOperation.create_image_api_license(email)

        return locked_user


class EmailManager:
    RESET_PASSWORD = 'reset_password'
    CONFIRM_EMAIL = 'confirm_email'
    NOTIFICATION_OVERFLOW = 'notification_overflow'
    NOTIFICATION_PRESENCE = 'notification_presence'

    URL_PATTERNS = {
        RESET_PASSWORD: settings.RESET_PASSWORD_URL,
        CONFIRM_EMAIL: settings.CONFIRM_URL,
    }

    @classmethod
    def __get_url(cls, email_key: str, **kwargs) -> str:
        url_pattern = cls.URL_PATTERNS.get(email_key)
        if not url_pattern:
            return ''
        return cls.URL_PATTERNS[email_key].format(**kwargs)

    @classmethod
    def send_email(cls, email_key: str, user: User = AnonymousUser(), email: Optional[str] = None, context: dict = {}):
        if isinstance(user, AnonymousUser):
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return
        else:
            email = user.email

        confirmation_token = default_token_generator.make_token(user)

        mail_template = EmailTemplate.objects.get(template_key=email_key)

        template = Template(mail_template.body)

        context.update(settings.EMAIL_CONTEXT)

        subject = mail_template.subject.format(**context)
        context = Context({
            **context,
            'username': user.username,
            f'{email_key}_url': cls.__get_url(email_key, user_id=str(user.id), confirmation_token=confirmation_token),
        })

        attachments = []
        for blob, image_name in context.get('blobs', []):
            image = MIMEImage(base64.b64decode(blob))
            image.add_header('Content-Disposition', f"attachment; filename= {image_name}.jpeg")
            attachments.append(image)

        data = {
            'subject': subject,
            'body': template.render(context),
            'from_email': settings.EMAIL_FROM,
            'to': [email],
            'alternatives': [(template.render(context), "text/html")],
            'attachments': attachments
        }

        EmailThread(data).start()


class EmailThread(threading.Thread):
    def __init__(self, mail_data: dict):
        self.mail_data = mail_data
        threading.Thread.__init__(self)

    def run(self):
        msg = EmailMultiAlternatives(**self.mail_data)
        msg.send()


class WorkspaceManager:
    DEFAULT_CONFIG = {
        'is_active': True,
        'template_version': settings.DEFAULT_TEMPLATES_VERSION,
        'features': {
            'retail_analytics': {
                'enabled': True,
            }
        },
        "activity_score_threshold": settings.DEFAULT_SCORE_THRESHOLD_VALUE,
        "notification_score_threshold": settings.DEFAULT_SCORE_THRESHOLD_VALUE,
        'sample_ttl': settings.SAMPLE_TTL,
        'activity_ttl': settings.ACTIVITY_TTL
    }

    @staticmethod
    def get_workspace_from_access(access_id: str) -> Workspace:
        return Access.objects.get(id=access_id).workspace

    @staticmethod
    def get_workspace(workspace_id: str) -> Workspace:
        return Workspace.objects.get(id=workspace_id)

    @staticmethod
    def lock_workspace(workspace: Workspace) -> Workspace:
        return Workspace.objects.select_for_update().get(id=workspace.id)

    @staticmethod
    def get_template_version(workspace_id: str) -> str:
        return Workspace.objects.get(id=workspace_id).config.get('template_version')

    @classmethod
    def update_workspace_config(cls, workspace: Workspace, config: dict) -> dict:
        locked_ws = cls.lock_workspace(workspace)
        ws_config = locked_ws.config
        ws_config.update(config)

        if not is_valid_json(ws_config, workspace_config_scheme):
            raise InvalidJsonRequest

        locked_ws.config.update(config)
        locked_ws.save()
        return ws_config

    @staticmethod
    def get_enabled_features(workspace: Workspace) -> List[str]:
        ws_config = workspace.config

        enabled_features = [name for name, config in ws_config["features"].items()
                            if config.get('enabled')]

        return enabled_features

    @classmethod
    def is_retail(cls, workspace: Workspace) -> bool:
        features = cls.get_enabled_features(workspace)
        return "retail_analytics" in features

    @staticmethod
    def create_workspace(title: str,
                         config: Optional[dict] = None,
                         username: Optional[str] = None,
                         password: Optional[str] = None,
                         analytics_types: Optional[List[str]] = None) -> Workspace:
        if analytics_types is None:
            analytics_types = []
        if config is None:
            config = WorkspaceManager.DEFAULT_CONFIG

        if not is_valid_json(config, workspace_config_scheme):
            raise InvalidJsonRequest()

        with transaction.atomic():
            workspace = Workspace.objects.create(title=title, config=config)
            workspace_id = str(workspace.id)
        if username and password:
            for analytics_type in analytics_types:
                execute.send_task("user_domain.tasks.sign_up_kibana", kwargs={
                    'username': username,
                    'password': password,
                    'workspace_id': workspace_id,
                    'analytics_type': analytics_type
                })

        return workspace

    @staticmethod
    def create_qa_workspace(title: str, username: Optional[str] = None, password: Optional[str] = None,
                            analytics_types: Optional[List[str]] = None) -> Workspace:
        config = WorkspaceManager.DEFAULT_CONFIG

        with transaction.atomic():
            workspace = Workspace.objects.create(title=title, config=config)

        for analytics_type in analytics_types:
            execute.send_task("user_domain.tasks.sign_up_kibana", kwargs={
                'username': username,
                'password': password,
                'workspace_id': str(workspace.id),
                'analytics_type': analytics_type
            })

        return workspace

    @classmethod
    def deactivate_workspace(cls, workspace: Workspace):
        with transaction.atomic():
            cls.update_workspace_config(
                workspace, {'is_active': False, 'deactivation_date': datetime.now().isoformat()}
            )

    @classmethod
    def activate_workspace(cls, workspace: Workspace):
        with transaction.atomic():
            cls.update_workspace_config(workspace, {'is_active': True, 'deactivation_date': None})


class AccessManager:
    @staticmethod
    def create_access(user: User, workspace: Workspace, permissions: Optional[str] = None) -> Access:
        permissions = permissions if permissions else 'AD'
        access = Access.objects.create(user=user, workspace=workspace, permissions=permissions)
        return access

    @staticmethod
    def get_owner_access(workspace_id: str) -> Access:
        return Access.objects.get(workspace_id=workspace_id, permissions=Access.OWNER)
