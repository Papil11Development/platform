import requests
from django.conf import settings
import json
import uuid
import platform_lib.utils
from user_domain.models import User, Workspace
from platform_lib.managers import KibanaManager
from platform_lib.exceptions import KibanaError


@platform_lib.utils.elk_checker
def get_kibana_password(user: User):
    password = None
    accesses = user.accesses.filter(workspace__config__kibana_password__isnull=False)
    if accesses.exists():
        password = accesses.first().workspace.config.get('kibana_password')

    return password


@platform_lib.utils.elk_checker
def change_kibana_password(username: str, password: str):
    data = {'password': password}
    url_post = f'{settings.ELASTIC_URL_EXT}/_security/user/{username}/_password'
    try:
        response = requests.post(url_post, headers=settings.ELASTIC_HEADERS_EXT, data=json.dumps(data),
                                 timeout=settings.HTTP_REQUEST_TIMEOUT)
    except requests.Timeout:
        raise KibanaError("Error when changing the password in Kibana")
    if response.json().get('error'):
        raise KibanaError("Error when changing the password in Kibana")


@platform_lib.utils.elk_checker
def create_space_elk(username, password, space_id, title, analytics_type):
    kibana = KibanaManager(settings.KIBANA_URL_EXT, headers=settings.ELASTIC_HEADERS_EXT)

    delete_list = []

    def delete_on_error():
        if delete_list:
            for url_to_delete in delete_list:
                requests.delete(url_to_delete, headers=settings.ELASTIC_HEADERS_EXT)
                print('An error has occurred. The changes made have been canceled!')
            raise Exception

    def create_user():
        data = {'password': f'{password}',
                'roles': [f'{username}']}
        url_post = f'{settings.ELASTIC_URL_EXT}/_security/user/{username}'
        check = check_exist(username, 'user')
        if not check:
            response = requests.post(url_post, headers=settings.ELASTIC_HEADERS_EXT, data=json.dumps(data))
            if 'error' in response.json().keys():
                delete_on_error()

    def check_exist(role_name, what):
        url_check = f'{settings.ELASTIC_URL_EXT}/_security/{what}/{role_name}'
        response = requests.get(url_check, headers=settings.ELASTIC_HEADERS_EXT)
        if response.json().get(role_name, False):
            return response.json()
        else:
            return {}

    def create_roles(space_id, new_index_pattern):
        data = {"cluster": [],
                "indices": [
                    {"names": [new_index_pattern], "privileges": ["all"], "allow_restricted_indices": False}],
                "applications": [{"application": "kibana-.kibana",
                                  "privileges": ["feature_dashboard.all",
                                                 "feature_canvas.all",
                                                 "feature_maps.all",
                                                 "feature_visualize.all",
                                                 "feature_discover.all"],
                                  "resources": [f"space:{space_id}"]}]}
        url_post = f'{settings.ELASTIC_URL_EXT}/_security/role/{username}'

        check = check_exist(username, 'role')
        if not check:
            response = requests.post(url_post, headers=settings.ELASTIC_HEADERS_EXT,
                                     data=json.dumps(data))
        else:
            spaces = check.get(username, {})['applications'][0].get('resources')
            space_ids = [elem.split(":")[1] for elem in spaces]
            if space_id not in space_ids:
                check[username]['applications'][0]['resources'].append(f'space:{space_id}')
            check[username]['indices'].append({
                "names": [new_index_pattern],
                "privileges": ["all"],
                "allow_restricted_indices": False
            })

            response = requests.put(url_post, headers=settings.ELASTIC_HEADERS_EXT,
                                    data=json.dumps(check[username]))
        if 'error' in response.json().keys():
            delete_on_error()
        delete_list.append(url_post)

    def create_elastic_index(analytics_type):
        index_id = str(uuid.uuid4())
        url = f'{settings.ELASTIC_URL_EXT}/{index_id}'
        with open(settings.MAPPING_JSON_PATH, 'r') as file:
            mapping = json.loads(file.read())[analytics_type]
        try:
            response = requests.put(url, headers=settings.ELASTIC_HEADERS_EXT, data=json.dumps(mapping))
        except KeyError:
            delete_on_error()
        check = response.json()
        if 'error' in check.keys():
            delete_on_error()
        delete_list.append(f'{settings.ELASTIC_URL_EXT}/{index_id}')
        return index_id

    kibana.create_space(space_id, title)
    index_id = create_elastic_index(analytics_type)

    with open(settings.INDEX_PATTERN_JSON_PATH, 'r') as file:
        pattern_data = json.load(file)[analytics_type]
    pattern_data['attributes']['title'] = index_id

    kibana.create_index_pattern(index_id, pattern_data, space_id)
    kibana.change_space_settings(index_id, space_id)

    try:
        dashboard_data = kibana.export_dashboard(settings.SAMPLE_BOARD[analytics_type])
    except KibanaError:
        with open(settings.SAMPLE_BOARD_JSON_PATH, 'r') as file:
            dashboard_data = json.load(file)[analytics_type]

    kibana.import_dashboard(dashboard_data, space_id, index_id, title=settings.DASHBOARDS_TITLES_MAP[analytics_type],
                            dashboard_id=analytics_type)

    create_roles(space_id, str(index_id))
    create_user()
    data = {
        'space_id': space_id,
        'index_id': index_id,
        'dashboard': analytics_type,
    }

    platform_lib.utils.UsageAnalytics(
        operation='create_ws_elk',
        username=username,
        space_id=data["space_id"]
    ).start()

    return data
