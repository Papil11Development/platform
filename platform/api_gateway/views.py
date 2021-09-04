import re
import uuid
import json
import base64
import traceback
from io import BytesIO
from datetime import datetime, timedelta
from typing import Union, Optional, List, Dict, Tuple
from PIL import Image, UnidentifiedImageError
from django.apps import apps
from django.http import HttpRequest

from django.views.decorators.cache import cache_control
from graphql import GraphQLError
from strawberry.django.views import GraphQLView
from strawberry.types.graphql import OperationType

from graphql.error import GraphQLSyntaxError
from strawberry.http import GraphQLHTTPResponse
from strawberry.types import ExecutionResult
from strawberry.schema.exceptions import InvalidOperationTypeError

import platform_lib.exceptions as exceptions

import jsonref
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.views.generic import View
from django.core.exceptions import ValidationError, ObjectDoesNotExist, BadRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import patch_vary_headers
from django.http.response import HttpResponseBadRequest, HttpResponse, JsonResponse, HttpResponseNotAllowed, \
    HttpResponseRedirect

from notification_domain.managers import NotificationManager
from platform_lib.managers import RealtimeImageCacheManager, ActivityProcessManager, RawProcessManager
from collector_domain.managers import AgentManager
from person_domain.tasks import duplicate_persons
from user_domain.managers import LoginManager
from user_domain.models import Workspace
from data_domain.managers import OngoingManager, SampleManager
from person_domain.managers import PersonManager
from person_domain.models import Person, Profile
from data_domain.models import Activity, Blob, BlobMeta, Sample
from data_domain.tasks import reidentification
from platform_lib.validation import is_valid_json
from notification_domain.models import Trigger, Notification, Endpoint
from label_domain.models import Label
from platform_lib.utils import utcnow_with_tz, UsageAnalytics, SampleObjectsName
from platform_lib.validation.schemes import activation_schema
from platform_lib.exceptions import TokenExpired, TemplateValidationError, InvalidSignature, InvalidClientTimestamp, \
    InvalidJsonRequest, AgentIsBlocked, WorkspaceInactive, InvalidToken, EmptyToken
from collector_domain.models import Agent, Camera, AttentionArea
from activation_manager.utils import catch_exception, encode_license
from activation_manager.models import Activation, find_last_activation
from activation_manager.certificate import validate_certificate, generate_certificate
from api_gateway.api.utils import authorization, cors_resolver, set_cookies, get_access, check_workspace
from api_gateway.api.token import Token
from notification_domain.tasks import triggers_handler


class TemporalHttpResponse(JsonResponse):
    status_code = None

    def __init__(self) -> None:
        super().__init__({})


@method_decorator([csrf_exempt, ], name='dispatch')
class APIView(GraphQLView):
    def should_render_graphiql(self, request: HttpRequest) -> bool:
        if request.method.lower() != "get":
            return False

        # This method is overridden because of the `workspace_id` in QUERY_STRING
        if self.allow_queries_via_get and request.META.get("QUERY_STRING"):
            return False

        return any(
            supported_header in request.META.get("HTTP_ACCEPT", "")
            for supported_header in ("text/html", "*/*")
        )

    def dispatch(self, request, *args, **kwargs):
        # Call '__options' method before 'super().dispatch' otherwise '__options' will never be invoked.
        if request.method == 'OPTIONS':
            return self.__options(request, *args, **kwargs)

        if not self.is_request_allowed(request):
            return HttpResponseNotAllowed(
                ["GET", "POST"], "GraphQL only supports GET and POST requests."
            )

        if self.should_render_graphiql(request):
            return self._render_graphiql(request)

        request_data = self.get_request_data(request)

        sub_response = TemporalHttpResponse()
        context = self.get_context(request, response=sub_response)
        root_value = self.get_root_value(request)

        method = request.method
        allowed_operation_types = OperationType.from_http(method)

        if not self.allow_queries_via_get and method == "GET":
            allowed_operation_types = allowed_operation_types - {OperationType.QUERY}

        try:
            result = self.schema.execute_sync(
                request_data.query,
                root_value=root_value,
                variable_values=request_data.variables,
                context_value=context,
                operation_name=request_data.operation_name,
                allowed_operation_types=allowed_operation_types,
            )
        except InvalidOperationTypeError as e:
            raise BadRequest(e.as_http_error_reason(method)) from e

        response_data = self.process_result(request=request, result=result)

        response = self._create_response(
            response_data=response_data, sub_response=sub_response
        )

        origin = request.META.get('HTTP_ORIGIN')

        if origin is not None and 'HTTP_TOKEN' in request.META:
            self.__set_cors_headers(response, origin)

        if request.user.is_authenticated:
            cookies = {'username': request.user.username, 'user_status': 'logged_in'}
        else:
            cookies = {'user_status': 'logged_out'}

        set_cookies(cookies, response)

        return response

    @classmethod
    def __options(cls, request, *args, **kwargs):
        # CORS 'preflighted' request handling.
        response = HttpResponse()
        headers = set(
            h.strip().lower() for h in request.META.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', str()).split(','))
        origin = request.META.get('HTTP_ORIGIN')

        if 'token' in headers and origin is not None:
            cls.__set_cors_headers(response, origin)

        return response

    @classmethod
    def __set_cors_headers(cls, response, origin):
        response['Access-Control-Allow-Origin'] = origin
        response['Access-Control-Allow-Methods'] = 'GET, POST'
        response['Access-Control-Allow-Headers'] = 'TOKEN, Content-Type'

        return response

    # TODO remove after front fix
    @staticmethod
    def format_error(error):
        try:
            if isinstance(error, GraphQLError):
                try:
                    error_dict = json.loads(error.message)
                    return {"message": error_dict["message"], "code": error_dict["code"]}
                except Exception:
                    return {"message": error.message}
            if isinstance(error, GraphQLSyntaxError):
                return error.formatted
        except Exception as e:
            return exceptions.format_internal_error(e)
        return exceptions.format_internal_error(error)

    def process_result(self, request: HttpRequest, result: ExecutionResult) -> GraphQLHTTPResponse:
        data: GraphQLHTTPResponse = {"data": result.data}

        if result.errors:
            data["errors"] = [self.format_error(err) for err in result.errors]
        if result.extensions:
            data["extensions"] = result.extensions

        return data


@method_decorator([csrf_exempt, cors_resolver, authorization(['access', 'agent']), check_workspace, ], name='dispatch')
class PostProcess(View):
    process_key = 'processes'
    process_type = 0
    oneshot_type = 1

    def post(self, request, *args, **kwargs):
        if not request.content_type == 'multipart/form-data':
            return HttpResponseBadRequest(json.dumps({'errors': 'Content-Type must be multipart/form-data'}))

        workspace = kwargs.get('workspace')
        token: Token = kwargs.get('token')

        if token.is_activation():
            agent = Agent.objects.get(activations=Activation.objects.get(id=token.id))
        elif token.is_agent():
            agent = Agent.objects.get(id=token.id)
        else:
            return HttpResponseBadRequest(json.dumps({'errors': 'Authorization failed'}))

        data = self.__parse_request(request)

        if not data:
            return HttpResponse(json.dumps({'errors': 'Data is empty.'}))

        self.__update_agent_status_info(agent)

        try:
            sample, is_raw = RawProcessManager.decode(data)
            if is_raw:
                sample.update(RawProcessManager.parse_extra(request.POST))
        except Exception:
            traceback.print_exc()
            return HttpResponseBadRequest(json.dumps({'errors': 'Data must have "Network Sample" format.'}))

        sample_type = self.__get_sample_type(sample)
        if sample_type == self.process_type and not sample.get('processes'):
            return HttpResponse(json.dumps({'errors': 'Processes is empty.'}))

        if RawProcessManager.is_media_process(sample['processes']):
            self.__update_or_create_media_activity(sample, workspace, agent)
            return HttpResponse(json.dumps({'data': 'Media has been posted.'}))

        humans_pack = RawProcessManager.parse_human_processes(sample['processes'])
        details = {'succeed': 0, 'failed': 0, 'ongoings': 0, 'total': len(humans_pack)}
        ongoings = []
        for human in humans_pack:
            human_process_manager = ActivityProcessManager(human)
            rois = human_process_manager.get_roi_process()
            if rois:
                self.__get_or_create_roi(rois, workspace, agent)

            try:
                if human_process_manager.is_activity_finalized() and human_process_manager.get_person_id():
                    UsageAnalytics(
                        username=workspace.accesses.first().user.username,
                        operation='activity',
                        meta={'device': str(agent.id)}
                    ).start()
                    activity, need_reid = self.__create_activity_record(human, workspace, agent)
                    # TODO move sample creation in activity when update activity meta
                    self.__create_samples_by_activity(workspace.id, activity)

                    if activity:
                        details['succeed'] += 1
                        if need_reid:
                            PostProcess.__reidentify(activity)
                else:
                    ongoings.append(human)
                    details['ongoings'] += 1
            except Exception:
                details['failed'] += 1
                traceback.print_exc()
        if ongoings:
            self.__create_ongoings(ongoings, workspace, agent)

        if details['failed']:
            return HttpResponseBadRequest(json.dumps({'errors': 'Failed record creation.', 'details': details}))

        return HttpResponse(json.dumps({'data': 'Data has been posted.', 'details': details}))

    @classmethod
    def __create_samples_by_activity(cls, workspace_id: Union[str, uuid.UUID], activity: Activity):
        # TODO Extend with another sample types
        def __parce_face_process_info_in_sample(face_process: Dict) -> Dict:
            # TODO use activity data manager when it merged
            face_embeddings = face_process['object'].get('embeddings', {})

            templates_to_create = []
            regex = re.compile('template')
            for key in face_embeddings.keys():
                if regex.search(key):
                    templates_to_create.append(key)

            face_object = {
                'id': 1,  # TODO replace hardcoded value
                'class': 'face',
            }

            if templates_to_create:
                face_object['templates'] = {template_version: face_embeddings[template_version]
                                            for template_version in templates_to_create}

            if crop_image := face_process.get('$best_shot'):
                face_object['$cropImage'] = crop_image

            if age := face_process['object'].get('age'):
                face_object['age'] = age

            if gender := face_process['object'].get('gender'):
                face_object['gender'] = gender

            if quality := face_process['object'].get('quality'):
                face_object['quality'] = quality

            return {
                f'objects@{SampleObjectsName.PROCESSING_CAPTURER}': [face_object]
            }

        face_process = cls.__get_face_process(activity.data)
        if face_process:
            face_sample_meta = __parce_face_process_info_in_sample(face_process)
            face_sample = Sample.objects.create(workspace_id=workspace_id, meta=face_sample_meta)
            face_process['sample_id'] = str(face_sample.id)

        activity.save()

    @staticmethod
    def __update_agent_status_info(agent: Agent):
        with transaction.atomic():
            AgentManager.update_or_activate_agent(agent.id)

    @staticmethod
    def __parse_request(request):
        raw_data = request.body
        if len(request.FILES):
            data = request.FILES.get('sample', list(request.FILES.values())[0])
            return data.read()
        elif len(request.POST):  # C++ specific parsing
            boundary_size = 40
            before_data = 5  # control symbols
            after_data = boundary_size + 8  # control symbols
            key = list(request.POST.keys())[0]
            key_index = raw_data.find(key.encode())
            data = raw_data[key_index + len(key) + before_data:-after_data]
            return data

    @staticmethod
    @transaction.atomic
    def __update_or_create_media_activity(sample: dict, workspace: Workspace, agent: Agent) -> Activity:
        try:
            activity = Activity.objects.select_for_update().get(
                data__processes__0__id=sample.get('processes')[0].get('id'))
            if sample.get('processes')[0].get('time_interval')[1]:
                activity.data['processes'][0]['time_interval'][1] = \
                    sample.get('processes')[0].get('time_interval')[1]
                activity.save()
        except ObjectDoesNotExist:
            activity = Activity.objects.create(data=sample, creation_date=utcnow_with_tz(), workspace=workspace)
            camera = Camera.objects.get(agent=agent.id)
            activity.camera = camera
            activity.save()
        return activity

    @classmethod
    @transaction.atomic
    def __create_activity_record(cls, sample: dict, workspace: Workspace, agent: Agent) -> Tuple[Activity, bool]:
        if not RawProcessManager.validate_sample_meta(
                {k: v for k, v in sample.items() if not k.startswith(RawProcessManager.bsm_indicator)}
        ):
            raise ValidationError('Validation error. Meta failed.')

        sample_type = cls.__get_sample_type(sample)
        meta, bsms = RawProcessManager.extract_bsms(sample)
        activity = None
        context = {}
        # match_data = PostProcess.__get_parent_process(sample).get('object').get('match_data')
        # if match_data and match_data.get('score', 1) >= workspace.config.get('activity_score_threshold',
        #                                                                      settings.DEFAULT_SCORE_THRESHOLD_VALUE):
        #     need_reid = False
        #     person_id = PostProcess.__get_parent_process(sample).get('object').get('id')
        # elif match_data:
        #     need_reid = False
        #     person_id = None
        # else:
        #     need_reid = True
        #     person_id = None

        person_id = None
        need_reid = True

        if sample_type == PostProcess.process_type:
            activity_id = PostProcess.__get_parent_process(sample).get('id')
            activity = Activity.objects.create(
                id=activity_id, data={}, creation_date=utcnow_with_tz(), workspace=workspace,
                person_id=person_id
            )

            camera = Camera.objects.get(agent=agent.id)
            activity.camera = camera
            context['activity_id'] = str(activity.id)

        created_bsms = cls.__create_bsms(bsms, workspace, context)
        meta = RawProcessManager.substitute_bsms(meta, created_bsms)

        if not RawProcessManager.validate_sample_meta(meta):
            raise ValidationError('Validation error. Sample failed')

        assert activity, 'Not implemented type'

        if sample_type == cls.process_type:
            activity.data = meta
            activity.save()

            return activity, need_reid

        return None, False

    @classmethod
    def __reidentify(cls, activity: Activity):
        try:
            reidentification.delay(activity.id)
        except Exception:
            traceback.print_exc()

    @staticmethod
    def __create_bsms(bsms: list, workspace: Workspace, context: dict) -> list:
        written_bsms = []
        for key, bsm, _ in bsms:
            blob = bsm.pop('blob', b'')
            blob_type = None

            assert isinstance(blob, bytes), 'Blob data should be a bytes object'

            if bsm.get('encoding', '') == 'base64':
                blob = base64.b64decode(blob)
                bsm.pop('encoding')

            if key == "$best_shot":
                blob_type = 'image'
            elif key.startswith(RawProcessManager.bsm_indicator):
                blob_type = key.replace(RawProcessManager.bsm_indicator, '')

            blob_obj = Blob.objects.create(data=blob)
            blob_meta = BlobMeta.objects.create(workspace=workspace, blob=blob_obj,
                                                meta={**bsm, **context, 'type': blob_type})

            written_bsms.append({'id': str(blob_meta.id)})

        return written_bsms

    @classmethod
    def __get_sample_type(cls, sample: dict):
        if cls.process_key in sample:
            return cls.process_type
        return cls.oneshot_type

    @classmethod
    @transaction.atomic
    def __create_ongoings(cls, ongoings: List[dict], workspace: Workspace, agent=None) -> None:
        camera = Camera.objects.get(agent=agent) if agent else None
        location = camera.locations.first() if camera else None
        camera_id = str(camera.id) if camera else ''
        location_id = str(location.id) if location else ''

        only_humans = []
        for ongoing in ongoings:
            ongoing_manager = ActivityProcessManager(ongoing)
            human = ongoing_manager.get_human_process()
            rois = ongoing_manager.get_roi_process()

            rois_lst = []
            for roi in rois:
                camera_roi_id = roi.get('object', {}).get('id', '')
                roi_title = roi.get('object', {}).get('name', '')

                if not ongoing_manager.is_process_finalized(roi) and camera_roi_id and roi_title:
                    rois_lst.append({'camera_roi_id': camera_roi_id, 'title': roi_title})

            face_best_shot = ongoing_manager.get_face_best_shot()
            body_best_shot = ongoing_manager.get_body_best_shot()

            # TODO remove when agent send profile_id
            profile_model = apps.get_model('person_domain', 'Profile')
            person_id = human['object']['id']

            try:
                profile_id = str(profile_model.objects.get(person_id=person_id).id)
            except ObjectDoesNotExist:
                profile_id = None

            human['object']['profile_id'] = profile_id

            # Face best shot for front body position
            cache_condition = face_best_shot and profile_id

            if cache_condition:
                RealtimeImageCacheManager.set_realtime_image_cache(profile_id, face_best_shot, body_best_shot)

            only_humans.append({'processes': [human],
                                'location_id': location_id,
                                'rois': rois_lst,
                                'camera_id': camera_id,
                                'have_face_best_shot': True if cache_condition else False,
                                'have_body_best_shot': True if body_best_shot and cache_condition else False,
                                })

        OngoingManager.set_ongoings(only_humans, str(workspace.id), camera_id)
        triggers_handler.delay(str(workspace.id))

    # TODO: Move to activity data manager?
    @staticmethod
    def __get_parent_process(sample: dict) -> dict:
        return next(filter(lambda track: track.get('object', {}).get('class', '') == 'human', sample['processes']), {})

    @staticmethod
    def __get_face_process(sample: dict) -> dict:
        return next(filter(lambda track: track.get('object', {}).get('class', '') == 'face', sample['processes']), {})

    @staticmethod
    def __get_or_create_roi(rois: list, workspace: Workspace, agent: Agent):
        camera = Camera.objects.get(agent=agent.id)
        roi_ids = []

        for roi in rois:
            camera_roi_id = roi.get('object', {}).get('id', '')
            roi_title = roi.get('object', {}).get('name', '')

            if not camera_roi_id or not roi_title:
                continue

            try:
                exist_roi = AttentionArea.objects.get(info__title=roi_title, workspace=workspace, camera=camera)
                if exist_roi and camera_roi_id != exist_roi.info.get("camera_roi_id"):
                    with transaction.atomic():
                        lock_roi = AttentionArea.objects.select_for_update().get(
                            info__title=roi_title, workspace=workspace, camera=camera)
                        lock_roi.info.update({"camera_roi_id": camera_roi_id})
                        lock_roi.save()
                        roi_ids.append(lock_roi.id)
                        continue
            except AttentionArea.DoesNotExist:
                pass

            try:
                roi = AttentionArea.objects.get(info__camera_roi_id=camera_roi_id, workspace=workspace, camera=camera)
            except AttentionArea.DoesNotExist:
                roi = AttentionArea.objects.create(id=uuid.uuid4(), workspace=workspace, camera=camera,
                                                   info={'camera_roi_id': camera_roi_id, 'title': roi_title})
            roi_ids.append(roi.id)

        return roi_ids


@method_decorator([csrf_exempt, catch_exception], name='dispatch')
class ActivationView(View):
    def post(self, request):
        data = json.loads(request.body)
        certificate = data['Certificate']
        request_b64 = data['Request']

        validate_certificate(certificate, request_b64, settings.PUBLIC_KEY_REQUEST, settings.LICENSE_SIGNATURE_TOOL)

        activation_data = jsonref.loads(base64.b64decode(data['Request']).decode())

        response_data = self.__activate_by_token(activation_data)

        _license = encode_license(json.dumps(response_data))
        return JsonResponse(
            data={
                'License': _license,
                'Certificate': generate_certificate(_license, settings.PRIVATE_KEY_RESPONSE,
                                                    settings.PUBLIC_KEY_RESPONSE,
                                                    settings.LICENSE_SIGNATURE_TOOL)
            })

    @classmethod
    def __get_agent(cls, token: str):
        token = Token.from_string(token)
        try:
            return Agent.objects.get(id=token.id) if token.is_agent() else Activation.objects.get(id=token.id).agent
        except (Agent.DoesNotExist, Activation.DoesNotExist):
            raise InvalidToken()

    @classmethod
    def __activate_by_token(cls, activation_data):
        action = activation_data['License']['Action']
        sign = activation_data['Signature']
        agent = cls.__get_agent(activation_data['License']['Token'])

        if not agent.is_active:
            raise AgentIsBlocked()

        workspace = agent.workspace

        if not workspace.config['is_active']:
            raise WorkspaceInactive()

        working_template = workspace.config.get('template_version', 'template10v100')

        custom_data = activation_data.get('CustomData')
        if custom_data:
            temp_list = custom_data['AvailableTemplates']
        else:
            temp_list = ['template6v6']

        if not is_valid_json(activation_data, activation_schema):
            raise InvalidJsonRequest()

        client_timestamp = float(activation_data['Timestamp'])
        if abs(client_timestamp - datetime.utcnow().timestamp()) > settings.ACTIVATION_MAX_TIME_DIFFERENCE:
            raise InvalidClientTimestamp

        new_activation = None

        if action == 'manually':
            if working_template not in temp_list:
                raise TemplateValidationError

            new_activation = Activation.objects.create(agent=agent, signature=sign)
        elif action == 'auto':
            token = Token.from_string(activation_data['License']['Token'])

            if not token:
                raise EmptyToken()

            activations = Activation.objects.filter(agent=agent).order_by('-creation_date')

            if not activations.filter(signature=sign).exists():
                raise InvalidSignature()

            parent_activation = find_last_activation(activations, token.id)

            if parent_activation is None:
                raise TokenExpired()

            new_activation = Activation.objects.create(
                signature=sign, agent=parent_activation.agent, previous_activation=parent_activation)

        response_data = {
            'Product': activation_data['Product'],
            'Device': {
                'Signature': activation_data['Signature'],
                'OS': activation_data['OS'],
                'Sensors': [dict(s) for s in activation_data['Sensors']]
            },
            'License': {
                'Version': '1.0',
                'Type': '',
                'Token': new_activation.token,
                'BeginTime': int(datetime.utcnow().timestamp()) - settings.ACTIVATION_MAX_TIME_DIFFERENCE,
                'EndTime': int(datetime.utcnow().timestamp()) +
                           workspace.config.get('offline_timeout', settings.DEFAULT_OFFLINE_TIMEOUT)
                           + settings.ACTIVATION_MAX_TIME_DIFFERENCE,
                'UpdateTimeout': settings.DEFAULT_UPDATE_TIMEOUT,
                'StoreLicense': workspace.config.get('store_license', False),
                'CustomData': {'WorkingTemplate': working_template}
            }
        }
        return response_data


@method_decorator([csrf_exempt, cors_resolver, authorization(['access', 'agent']), ], name='dispatch')
class GetNotifications(View):
    def get(self, request, workspace, *args, **kwargs):
        time_inaccuracy = 0.2

        notifications = Notification.objects.filter(workspace=workspace).order_by('-creation_date')

        info = []
        notifications_for_deletion = []
        for notification in notifications:

            notification_type = notification.meta.get('type')

            notification_info = {
                'id': str(notification.id),
                'type': notification_type,
                'locationTitle': notification.meta.get('location_title'),
                'locationId': notification.meta.get('location_id'),
                'isActive': notification.is_active,
                'isViewed': notification.is_viewed,
                'endpointSendingStatuses': notification.meta.get("statuses")
            }

            if notification_type == 'presence':
                try:
                    profile_info = Profile.objects.get(id=notification.meta['profile_id']).info
                except Exception as exception:
                    print(f"Exception: {exception} In handle notification with id: {notification.id}")
                    print(f"Trace: {traceback.format_exc()}")
                    notifications_for_deletion.append(str(notification.id))
                    continue

                notification_info.update({
                    'profileId': notification.meta.get('profile_id'),
                    'activityId': notification.meta.get('activity_id'),
                    'profileGroupId': notification.meta.get('profile_group_id'),
                    'description': profile_info.get('description'),
                    'mainSampleId': profile_info.get('main_sample_id'),
                    'realtimeFacePhotoId': notification.meta.get('realtime_face_photo_id'),
                    'realtimeBodyPhotoId': notification.meta.get('realtime_body_photo_id'),
                    'creationDate': notification.creation_date.isoformat(),
                })

            elif notification_type == 'location_overflow':
                if notification.last_modified < notification.creation_date + timedelta(seconds=time_inaccuracy):
                    continue

                notification_info.update({
                    'limit': notification.meta.get('limit'),
                    'currentCount': notification.meta.get('current_count'),
                    'creationDate': (notification.creation_date +
                                     timedelta(seconds=notification.meta['lifetime'])).isoformat(),
                })

            info.append(notification_info)

        context = {
            'notifications': info,
        }

        if notifications_for_deletion:
            NotificationManager(str(workspace.id)).delete(notifications_for_deletion)

        return HttpResponse(json.dumps(context))


@method_decorator([csrf_exempt, cors_resolver], name='dispatch')
class GetImage(View):
    @cache_control(public=True, max_age=3600)
    def get(self, request, sample_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponse(status=400, content='Permission denied')

        workspace_ids = request.user.accesses.values_list('workspace_id', flat=True)
        workspace_filter = Q(workspace_id__in=workspace_ids)

        try:
            uuid.UUID(sample_id)
        except ValueError:
            return HttpResponse(status=400, content='This is not a valid UUID')

        if Sample.objects.filter(id=sample_id).exists():
            sample = Sample.objects.get(id=sample_id)
            try:
                blobmeta_id = SampleManager.get_face_crop_id(sample.meta)
                image = BlobMeta.objects.get(id=blobmeta_id).blob.data.tobytes()
            except Exception as ex:
                print(ex)
                return HttpResponse(status=400, content='Person is anonymous')
        elif BlobMeta.objects.filter(id=sample_id).exists():
            blob_meta = BlobMeta.objects.get(id=sample_id)
            if blob_meta.meta.get('format') != 'IMAGE':
                return HttpResponse(status=400, content='This is not an image')
            image = blob_meta.blob.data.tobytes()
        else:
            return HttpResponse(status=400, content='This is not a valid UUID')
        try:
            extension = Image.open(BytesIO(image))
        except UnidentifiedImageError:
            return HttpResponse(status=400, content='This is not an image')

        response = HttpResponse(image, content_type=f'image/{extension.format.lower()}')
        response['ETag'] = sample_id
        response['Accept-Ranges'] = 'bytes'
        patch_vary_headers(response, ['Accept-Encoding'])
        return response


@method_decorator([csrf_exempt, cors_resolver], name='dispatch')
class GetRealtimeImage(View):
    def get(self, request, image_key, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponse(status=400, content='Permission denied')

        profile_model = apps.get_model('person_domain', 'Profile')
        profile_id = RealtimeImageCacheManager.get_profile_id_from_key(image_key)

        workspace_ids = request.user.accesses.values_list('workspace_id', flat=True)

        try:
            # check key owner
            profile_model.objects.get(id=profile_id, workspace_id__in=workspace_ids)
            image = RealtimeImageCacheManager.get_image_from_cache(image_key)
        except profile_model.DoesNotExist:
            image = None

        if not image:
            return HttpResponse(status=400, content='This is not a valid UUID or cache is empty')
        if isinstance(image, dict):
            image = image['blob']

        extension = Image.open(BytesIO(image))
        response = HttpResponse(image, content_type=f'image/{extension.format.lower()}')
        response['ETag'] = image_key
        response['Accept-Ranges'] = 'bytes'
        patch_vary_headers(response, ['Accept-Encoding'])
        return response


class GetAgentLink(View):
    def get(self, request, os_version, *args, **kwargs):
        url = ''
        if request.path.find('v1') != -1:
            url = settings.AGENT_DOWNLOAD_URL_V1.get(os_version, '')
        elif request.path.find('v2') != -1:
            url = settings.AGENT_DOWNLOAD_URL_V2.get(os_version, '')

        if url:
            UsageAnalytics(
                operation='agent_download',
                username=request.COOKIES.get('username'),
                meta={"os_version": os_version}
                ).start()
            return HttpResponseRedirect(url)
        else:
            return HttpResponse(status=404)


class ExternalLogin(View):
    def get(self, request, *args, **kwargs):
        login = request.GET.get('login')
        if login is None:
            return HttpResponseBadRequest()
        confirmation_token = request.GET.get('token')
        workspace_id = request.GET.get('workspace_id')

        LoginManager.auth(
            username=login, request=request,
            confirmation_token=confirmation_token,
            workspace_id=workspace_id,
            password=''
        )

        if request.user.is_authenticated:
            cookies = {'username': request.user.username, 'user_status': 'logged_in'}
        else:
            cookies = {'user_status': 'logged_out'}

        if workspace_id:
            response = HttpResponseRedirect(f'/dashboard/?workspace={workspace_id}')
        else:
            response = HttpResponseRedirect('/workspaces/')

        set_cookies(cookies, response)
        return response


@method_decorator([csrf_exempt, get_access(qa_only=True), ], name='dispatch')
class DuplicatePerson(View):
    def post(self, request, access):
        data = json.loads(request.body)
        count = data.get('count', 1)
        person_ids = data.get('person_ids', None)
        fast_mode = data.get('fast_mode', False)

        duplicate_persons.delay(access_id=access.id,
                                duplicate_count=count,
                                person_ids=person_ids,
                                fast_mode=fast_mode)

        return HttpResponse(json.dumps({'data': 'Task has been pushed.'}))
