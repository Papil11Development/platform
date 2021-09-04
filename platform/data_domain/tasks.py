import base64
import logging
import uuid
from datetime import datetime, timedelta
from functools import reduce
from typing import Optional, List

from celery import shared_task, execute
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Prefetch
from django.conf import settings
from celery import shared_task, execute
from main.celery import app


from data_domain.managers import ActivityManager, SampleManager

from requests.exceptions import ConnectionError as RequestConnectionError

from activation_manager.models import Activation
from collector_domain.models import Agent, AttentionArea, Camera
from data_domain.managers import ActivityManager, SampleManager
from data_domain.matcher.main import MatcherAPI
from data_domain.models import Activity, Sample, BlobMeta
from label_domain.models import Label
from main.celery import app
from main.settings import (DEFAULT_TEMPLATES_VERSION, PUBLIC_KIBANA_URL, DEFAULT_FAR_THRESHOLD_VALUE,
                           MATCHRESULT_BEST_QUALITY_THRESHOLD, MATCHRESULT_PASS_QUALITY_THRESHOLD)
from notification_domain.models import Endpoint, Notification, Trigger
from person_domain.models import Profile, Person
from platform_lib import elastic
from platform_lib.exceptions import InvalidToken
from platform_lib.exceptions import KibanaError
from platform_lib.managers import ActivityProcessManager
from platform_lib.types import ElasticAction
from platform_lib.utils import ActivityDocumentManager, UsageAnalytics, estimate_quality, utcnow_with_tz
from user_domain.api.utils import create_space_elk, get_kibana_password
from user_domain.models import Access
from user_domain.models import Workspace, User

logger = logging.getLogger(__name__)


analytics_funcs = {
    'retail_analytics': lambda ws, elk: retail_analytics(ws, elk),
    'advertising_analytics': lambda ws, elk: advertising_analytics(ws, elk),
}


def get_elastic_workspaces(workspace_ids: list = None):
    workspaces = Workspace.objects.filter(config__is_active=True, config__features__isnull=False)
    if workspace_ids:
        workspaces = workspaces.filter(id__in=workspace_ids)
    return workspaces


def prepare_activity_data(activity: Activity) -> dict:
    process_data = ActivityDocumentManager.get_process_data(activity.data.get('processes', []))
    if not process_data.get('time_start', ''):
        return {}
    location_id = ''
    location_title = ''
    if activity.camera and activity.camera.locations.exists():
        # TODO: think about the logic of several locations at activity in kibana.
        location = activity.camera.locations.first()
        location_id = location.id
        location_title = location.title

    activity_data = {
        **process_data,
        'id': str(activity.id),
        'creation_date': activity.creation_date.isoformat(),
        'location_id': str(location_id),
        'location_title': location_title,
        'is_staff': False
    }

    return activity_data


def get_media_for_activities(activity: Activity, time_interval: tuple) -> list:
    camera_id = activity.camera.id
    medias = Activity.objects.filter(data__processes__0__object__class='media', camera=camera_id)
    q = Q(data__processes__0__time_interval__0__lt=time_interval[1],
          data__processes__0__time_interval__0__gt=time_interval[0])

    q |= Q(data__processes__0__time_interval__0__lt=time_interval[0],
           data__processes__0__time_interval__1=None)

    q |= Q(data__processes__0__time_interval__1__isnull=False,
           data__processes__0__time_interval__0__lt=time_interval[0],
           data__processes__0__time_interval__1__gt=time_interval[0])

    medias = medias.filter(q)
    media_list = []
    for media in medias:
        media_list.append(media.data.get('processes')[0].get('object').get('name', ''))
    return media_list


def get_activities_batch(workspace_id: str, creation_date: Optional[datetime] = None) -> list:
    q = Q(workspace_id=workspace_id)
    if creation_date:
        q &= Q(creation_date__gt=creation_date)
    activities = Activity.objects.filter(q).select_related('camera').prefetch_related('camera__locations')
    activities = activities.order_by('creation_date')
    chunks = [activities[i:i + settings.BATCH_SIZE] for i in range(0, activities.count(), settings.BATCH_SIZE)]
    return chunks


def get_persons_batch(workspace_id: str) -> list:
    persons = Person.objects.filter(workspace_id=workspace_id)
    persons_count = persons.count()
    persons = persons.select_related('profile').prefetch_related(
        'profile__profile_groups',
        Prefetch('activities', queryset=Activity.objects.order_by('creation_date'))
    ).distinct().order_by('creation_date')
    chunks = [persons[i:i + settings.BATCH_SIZE] for i in range(0, persons_count, settings.BATCH_SIZE)]
    return chunks


def advertising_analytics(workspace_id: str, elk_index: str):
    latest_activity_date = elastic.Activity.get_last_elastic_activity(elk_index)
    chunks_activities = get_activities_batch(workspace_id, latest_activity_date)
    for activities in chunks_activities:
        for activity in activities:
            try:
                activity_data = prepare_activity_data(activity)
                if not activity_data:
                    continue
                parent_time_internal = ActivityProcessManager(activity.data).get_human_timeinterval()
                medias = get_media_for_activities(activity, parent_time_internal)
                activity_data['medias'] = medias
                act = elastic.Activity(**activity_data)
                act.save(index=elk_index)

            except Exception as exc:
                print('Unexpected exception occurred', exc)


def retail_analytics(workspace_id: str, elk_index: str):
    chunks = get_persons_batch(workspace_id=workspace_id)
    for persons in chunks:
        first_activities = [str(person.activities.first().id) for person in persons if person.activities.first()]
        for person in persons:
            activity_ids = elastic.Activity.get_elastic_activities(index=elk_index, person_id=str(person.id))
            activities = person.activities.exclude(id__in=activity_ids)
            activities = activities.select_related('camera').prefetch_related('camera__locations')
            for activity in activities:
                groups = [gr.title for gr in person.profile.profile_groups.all()] if hasattr(person, 'profile') else []
                try:
                    groups.remove("Staff")
                    is_staff = True
                except ValueError:
                    is_staff = False
                data = prepare_activity_data(activity)
                activity_data = {
                    **data,
                    'person_id': str(person.id),
                    'age': person.info.get('age'),
                    'gender': person.info.get('gender'),
                    'is_staff': is_staff,
                    'first_visit': str(activity.id) in first_activities,
                    'groups': groups
                }
                activity_data.pop('watcher', None)

                if None in [activity_data['age'], activity_data['gender']]:
                    continue

                try:
                    act = elastic.Activity(**activity_data)
                    act.save(index=elk_index)
                except Exception as exc:
                    print('Unexpected elastic exception occurred', exc)


def get_or_create_analytics(ws: Workspace, analytics_type: str) -> dict:
    feature = ws.config.get('features', {}).get(analytics_type, {})
    if feature.get('url') and feature.get('index'):
        return feature
    if not Activity.objects.filter(workspace_id=ws.id).exists():
        return {}

    with transaction.atomic():
        locked_ws = Workspace.objects.select_for_update().get(id=ws.id)
        user = locked_ws.accesses.first().user
        password = get_kibana_password(user)
        if not password:
            password = User.objects.make_random_password()
        try:
            data = create_space_elk(user.username, password, str(locked_ws.id), locked_ws.title, analytics_type)
        except Exception:
            raise KibanaError(f'Error when creating {analytics_type}.', workspace_id=str(ws.id))

        url_elk = f'{PUBLIC_KIBANA_URL}/s/{data["space_id"]}/app/dashboards#/view/{data["dashboard"]}'

        features = locked_ws.config.get('features', {})
        features[analytics_type] = {
            'enabled': True,
            'url': url_elk,
            'index': data['index_id'],
        }

        locked_ws.config.update({
            'kibana_password': password,
            'features': features,
        })

        # TODO: Deprecated. Remove after updating the frontend.
        if analytics_type == 'retail_analytics':
            locked_ws.config.update({
                'url_elk': url_elk,
                'elk_index_id': data['index_id']
            })
        locked_ws.save()
        return features[analytics_type]


@shared_task
def elastic_manager(action: ElasticAction, **kwargs):

    def __filter_tasks(task: dict, action: Optional[ElasticAction] = None, workspace_id: Optional[str] = None):
        expr = True
        task_info = task['request'] if task.get('request') else task

        if action:
            task_name = f'data_domain.tasks.elastic_{action.value}'
            expr &= task_info.get('name') == task_name
        else:
            task_name = 'data_domain.tasks.elastic_'
            expr &= task_info.get('name').startswith('data_domain.tasks.elastic_')
        if workspace_id:
            expr &= task_info.get('kwargs', {}).get('workspace_id') == workspace_id
        return expr

    inspect = app.control.inspect(['celery@elastic.action'])

    scheduled = inspect.scheduled()
    active = inspect.active()
    reserved = inspect.reserved()

    scheduled = reduce(lambda init, item: init + item, scheduled.values(), list()) \
        if scheduled is not None else []
    active = reduce(lambda init, item: init + item, active.values(), list()) \
        if active is not None else []
    reserved = reduce(lambda init, item: init + item, reserved.values(), list()) \
        if reserved is not None else []

    push_tasks = list(filter(
        lambda task: __filter_tasks(task, action=ElasticAction.push), scheduled + active + reserved
    ))

    action = ElasticAction(action)

    if action == ElasticAction.push:
        workspace_ids = kwargs.get('workspace_ids')
        q = Q(config__is_active=True)
        if workspace_ids:
            q &= Q(id__in=workspace_ids)

        for ws in Workspace.objects.filter(q):
            if list(filter(lambda task: __filter_tasks(task, workspace_id=str(ws.id)), push_tasks)):
                continue
            execute.send_task("data_domain.tasks.elastic_push", kwargs={'workspace_id': str(ws.id)})

    elif action == ElasticAction.drop:
        workspace_id = kwargs.get('workspace_id')
        person_ids = kwargs.get('person_ids', [])
        assert workspace_id, 'workspace_id must be specified.'

        workspace_tasks = filter(lambda task: __filter_tasks(task, ElasticAction.push, workspace_id), push_tasks)
        for task in workspace_tasks:
            task_id = task.get('id') or task.get('request', {}).get('id')
            app.control.revoke(task_id, terminate=True)

        execute.send_task("data_domain.tasks.elastic_drop", kwargs={
            'workspace_id': workspace_id,
            'person_ids': person_ids
        })


@shared_task
def elastic_push(workspace_id: str):
    ws = Workspace.objects.get(id=workspace_id, config__is_active=True)
    for analytics_type in analytics_funcs:
        feature = None
        if ws.config.get('features', {}).get(analytics_type, {}).get('enabled'):
            feature = get_or_create_analytics(ws, analytics_type)

        if feature:
            analytics_funcs[analytics_type](str(ws.id), feature['index'])


@shared_task
def clean_deactivated_workspaces():
    TASK_LIFETIME = 360
    QS_BATCH_SIZE = 5000

    def timeit_transaction_deleter_deco(f):
        def wrapper(*args):
            start_ts = datetime.now().timestamp()
            with transaction.atomic():
                res = f(*args)
            consumed_time = datetime.now().timestamp() - start_ts
            return res, round(consumed_time)
        return wrapper

    delete_after_delta = settings.WORKSPACE_CLEANING_DELTA
    workspaces = Workspace.objects\
        .filter(
            config__deactivation_date__isnull=False,
            config__deactivation_date__lte=(datetime.now()-delete_after_delta).isoformat(),
            config__is_active=False
        )

    @timeit_transaction_deleter_deco
    def model_cleaner(model, qs):
        p_pks = qs.values_list('pk')[:QS_BATCH_SIZE]
        return model.objects.filter(pk__in=p_pks).delete()

    def ws_filtered(model, ws):
        return model.objects.filter(workspace=ws)

    model_resolver_list = [
        (Person, ws_filtered), (Profile, ws_filtered), (Sample, ws_filtered),
        (Activity, ws_filtered), (BlobMeta, ws_filtered),
        (Activation, lambda model, ws: model.objects.filter(agent__workspace=ws)),
        (Agent, ws_filtered), (Camera, ws_filtered), (AttentionArea, ws_filtered),
        (Label, ws_filtered), (Endpoint, ws_filtered), (Trigger, ws_filtered),
        (Notification, ws_filtered), (Access, ws_filtered),
        (Workspace, lambda model, ws: model.objects.filter(id=ws.id)),
    ]

    task_time_sum = 0
    for ws in workspaces:
        for model_r in model_resolver_list:
            deleted_n = -1
            while deleted_n != 0:
                model = model_r[0]
                qs = model_r[1](model, ws)
                deleted_tuple, passed_time = model_cleaner(model, qs)
                deleted_n = deleted_tuple[0]
                logger.info(f'deleted! {deleted_n}')
                task_time_sum += passed_time
                if task_time_sum > TASK_LIFETIME:
                    return
        logger.info('cleaned!', ws)


@shared_task
def elastic_drop(person_ids: List[str], workspace_id: str):
    ws = Workspace.objects.get(id=workspace_id, config__is_active=True)
    index = ws.config.get('features', {}).get('retail_analytics', {}).get('index')
    if not index or not elastic.Activity.is_index_exist(index):
        return

    elastic.Activity.request_delete(index, person_ids)

    execute.send_task("data_domain.tasks.elastic_manager", kwargs={
        'action': ElasticAction.push,
        'workspace_ids': [workspace_id]
    })


@shared_task
def reidentification(activity_id: str):
    activity = Activity.objects.get(id=activity_id)
    data_manager = ActivityProcessManager(activity.data)

    def __get_data_for_matching(sample: Sample, template_version: str) -> dict:

        data = dict()
        for process in data_manager.get_face_processes():
            process_info = data_manager.get_process_info(process)

            template_id = process_info.get(f'${template_version}', {}).get('id')
            quality = process_info.get('quality')

        template_id = SampleManager.get_template_id(sample.meta, template_version)

        if template_id is None:
            return data

        face_crop_id = SampleManager.get_face_crop_id(sample.meta)
        quality = SampleManager.get_face_quality(sample.meta)

        source_blob = BlobMeta.objects.select_related('blob').get(id=template_id).blob.data
        source_template = base64.standard_b64encode(source_blob.tobytes()).decode()

        if quality is None and face_crop_id:
            quality = estimate_quality(template_version, face_crop_id)

        if quality > MATCHRESULT_PASS_QUALITY_THRESHOLD:
            data[source_template] = {
                'sample_id': str(sample.id),
                'quality': quality,
                'template_id': template_id
            }

        return data

    person_id = data_manager.get_person_id()
    try:
        uuid.UUID(person_id)
    except (ValueError, AttributeError):
        raise InvalidToken('Invalid human id')

    # if no face sample return
    try:
        face_sample = Sample.objects.get(id=(ActivityManager.get_face_processes(activity) or [{}])[0].get('sample_id'))
    except Sample.DoesNotExist:
        return

    ws_config = activity.workspace.config
    template_version = ws_config['template_version']
    activity_score_threshold = ws_config['activity_score_threshold']
    data_for_matching = __get_data_for_matching(face_sample, template_version)
    templates = list(data_for_matching.keys())

    response = MatcherAPI.search(
        str(activity.workspace_id),
        template_version,
        templates,
        nearest_count=1,
        score=activity_score_threshold
    )

    sorted_response = sorted(response, key=lambda it: data_for_matching[it.get('template')]['quality'], reverse=True)

    person = None
    profile = None

    for template_result in sorted_response:
        template = template_result.get('template')
        search_result = template_result.get('searchResult', [])
        template_id = data_for_matching[template]['template_id']
        source_quality = data_for_matching[template]['quality']
        sample_id = data_for_matching[template]['sample_id']
        person_meta = {
            'age': SampleManager.get_age(face_sample.meta),
            'gender': SampleManager.get_gender(face_sample.meta)
        }

        # Update sample quality after estimate
        SampleManager.update_face_object(face_sample.meta, {'quality': source_quality})
        face_sample.save()

        if search_result:
            with transaction.atomic():
                if settings.ENABLE_PROFILE_AUTOGENERATION:
                    profile = Profile.objects.select_for_update().get(person_id=search_result[0].get('personId'))
                    current_sample = Sample.objects.get(id=profile.info.get('main_sample_id'))
                    # for activity link
                    person = profile.person
                else:
                    person = Person.objects.select_for_update().get(id=search_result[0].get('personId'))
                    current_sample = Sample.objects.get(id=person.info.get('main_sample_id'))

                if source_quality > (SampleManager.get_face_quality(current_sample.meta) or 0):
                    person_meta['main_sample_id'] = sample_id
                    if settings.ENABLE_PROFILE_AUTOGENERATION:
                        profile.info.update(person_meta)  # TODO fix issue: new better photo will replace age, gender
                        profile.save()
                    else:
                        person.info.update(person_meta)
                        person.save()
                    # TODO: call async set-base
                    templates_info = [{'id': str(template_id), 'personId': str(person.id)}]
                    MatcherAPI.set_base_remove(str(activity.workspace.id), template_version, [str(person.id)])
                    MatcherAPI.set_base_add(str(activity.workspace.id), template_version, templates_info)

            break

        elif source_quality > MATCHRESULT_BEST_QUALITY_THRESHOLD:
            person_meta['main_sample_id'] = sample_id

            with transaction.atomic():
                person = Person.objects.create(id=person_id, workspace=activity.workspace, info=person_meta)
                if settings.ENABLE_PROFILE_AUTOGENERATION:
                    profile = Profile.objects.create(workspace=activity.workspace, person=person, info=person_meta)

            templates_info = [{'id': str(template_id), 'personId': str(person.id)}]
            MatcherAPI.set_base_add(str(activity.workspace.id), template_version, templates_info)
            break

    with transaction.atomic():
        if settings.ENABLE_PROFILE_AUTOGENERATION and profile:
            profile.samples.add(face_sample)
            profile.save()

        if person:
            activity = Activity.objects.select_for_update().get(id=activity.id)
            person.samples.add(face_sample)
            person.save()  # for update last_modified
            activity.person = person
            activity.save()


@shared_task(autoretry_for=(RequestConnectionError,),
             max_retries=4,
             retry_backoff=5,
             retry_backoff_max=700,
             retry_jitter=True)
def rebuild_index(index: str, template_version: str):
    MatcherAPI.set_base(index, template_version)


@shared_task(autoretry_for=(RequestConnectionError,),
             max_retries=4,
             retry_backoff=5,
             retry_backoff_max=700,
             retry_jitter=True)
def add_to_index(index: str, template_version: str, templates_info: list):
    MatcherAPI.set_base_add(index, template_version, templates_info)


@shared_task(autoretry_for=(RequestConnectionError,),
             max_retries=4,
             retry_backoff=5,
             retry_backoff_max=700,
             retry_jitter=True)
def remove_from_index(index: str, template_version: str, person_ids: list):
    MatcherAPI.set_base_remove(index, template_version, person_ids)


@shared_task(autoretry_for=(RequestConnectionError,),
             max_retries=4,
             retry_backoff=5,
             retry_backoff_max=700,
             retry_jitter=True)
def delete_index(index: str, template_version: str):
    MatcherAPI.delete_index(index, template_version)


@shared_task
def sample_retention_policy():

    def delete_samples(workspace_id: str, sample_ttl: int) -> int:
        with transaction.atomic():
            profile_samples_ids = Profile.objects.filter(
                samples__isnull=False,
                workspace_id=workspace_id
            ).values_list('samples', flat=True)

            activity_samples_ids = []
            for activity in Activity.objects.filter(workspace_id=workspace_id).iterator():
                activity_samples_ids += ActivityManager.get_samples_ids(activity)

            standalone_samples = Sample.objects.exclude(
                id__in=set(activity_samples_ids + list(map(str, profile_samples_ids)))
            )

            samples_to_delete = standalone_samples.filter(
                creation_date__lt=(utcnow_with_tz() - timedelta(seconds=sample_ttl or settings.SAMPLE_TTL)),
                workspace_id=workspace_id
            )
            return SampleManager.delete_samples(samples_to_delete)

    for workspace_id, sample_ttl in Workspace.objects.values_list('id', 'config__sample_ttl').iterator():
        try:
            num = delete_samples(workspace_id, sample_ttl)
        except Exception as ex:
            logger.error(f'ERROR: sample retention policy:workspace:{workspace_id}\n{ex}')
            continue
        if num:
            logger.info(f'Sample retention policy:workspace:{workspace_id} - {num} samples have been deleted.')
