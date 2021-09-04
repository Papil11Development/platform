import json
import logging
import requests
from typing import List

from user_domain.models import Workspace
from django.conf import settings

logger = logging.getLogger(__name__)


class MatcherAPI:
    @classmethod
    def set_base(cls, index_key: str, template_version: str):
        query = '''
        mutation($indexKey: String!, $templateVersion: String!)
            {
                setBase(indexKey: $indexKey, templateVersion: $templateVersion)
                    {ok, templatesCount}
            }'''
        variables = {'indexKey': index_key, 'templateVersion': template_version}
        operation = {'query': query, 'variables': variables}

        response = cls.__graph_request(operation)
        errors = response.get('errors')

        if errors is not None:
            logger.error(msg=f'FaceMatcher returned an error. {errors}')
            return {}

        search_data = response.get('data', {}).get('setBase', {}).get('templatesCount', {})

        return search_data if search_data is not None else {}

    @classmethod
    def set_base_add(cls, index_key: str, template_version: str, templates_info: list):
        query = '''
        mutation($indexKey: String!, $templateVersion: String!, $templatesInfo: [TemplateInfoType!]!)
            {
                setBaseAdd(indexKey: $indexKey, templateVersion: $templateVersion, templatesInfo: $templatesInfo)
                    {ok, templatesCount}
            }'''
        variables = {
            'indexKey': index_key,
            'templateVersion': template_version,
            'templatesInfo': templates_info
        }
        operation = {'query': query, 'variables': variables}

        response = cls.__graph_request(operation)
        errors = response.get('errors')

        if errors is not None:
            logger.error(msg=f'FaceMatcher returned an error. {errors}')
            return {}

        search_data = response.get('data', {}).get('setBaseUpdate', {}).get('templatesCount', {})

        return search_data if search_data is not None else {}

    @classmethod
    def set_base_remove(cls, index_key: str, template_version: str, person_ids: list):
        person_ids = list(map(str, person_ids))
        query = '''
        mutation($indexKey: String!, $templateVersion: String!, $personIds: [String!]!){
            setBaseRemove(indexKey: $indexKey, templateVersion: $templateVersion, personIds: $personIds)
                {ok, templatesCount}
        }
        '''
        variables = {
            'indexKey': index_key,
            'templateVersion': template_version,
            'personIds': person_ids
        }
        operation = {'query': query, 'variables': variables}

        response = cls.__graph_request(operation)
        errors = response.get('errors')

        if errors is not None:
            logger.error(msg=f'FaceMatcher returned an error. {errors}')
            return {}

        search_data = response.get('data', {}).get('setBaseUpdate', {}).get('templatesCount', {})

        return search_data if search_data is not None else {}

    @classmethod
    def search(cls,
               index_key: str,
               template_version: str,
               templates: List[str],
               nearest_count: int = 5,
               score: float = 0.0,
               far: float = 1.0,
               frr: float = 0.0) -> List[dict]:

        # TODO optimise network overhead
        query = '''
        query($indexKey: String!, $templateVersion: String!, $nearestCount: Int!, $templates: [Base64!]!,
                $score: Float!, $faR: Float! , $frR: Float!){
            search(
                indexKey: $indexKey,
                nearestCount: $nearestCount,
                templates: $templates,
                templateVersion: $templateVersion,
                score: $score,
                frR: $frR,
                faR: $faR
            ){
                template,
                searchResult{personId, matchTemplateId, matchResult{distance, faR, frR, score}}
            }
        }
        '''
        variables = {
            'indexKey': index_key,
            'templateVersion': template_version,
            'templates': templates,
            'nearestCount': nearest_count,
            'score': score,
            'faR': far,
            'frR': frr
        }

        operation = {'query': query, 'variables': variables}
        response = cls.__graph_request(operation)
        errors = response.get('errors')

        if errors is not None:
            logger.error(msg=f'FaceMatcher returned an error. {errors}')
            return []

        return response.get('data', {}).get('search', [])

    @classmethod
    def delete_index(cls, index_key: str, template_version: str):
        query = '''
            mutation($indexKey: String!, $templateVersion: String!)
                {
                    deleteIndex(indexKey: $indexKey, templateVersion: $templateVersion)
                        {ok}
                }'''
        variables = {'indexKey': index_key, 'templateVersion': template_version}
        operation = {'query': query, 'variables': variables}

        response = cls.__graph_request(operation)
        errors = response.get('errors')

        if errors is not None:
            logger.error(msg=f'FaceMatcher returned an error. {errors}')
            return False

        return response.get('data', {}).get('deleteIndex', {}).get('ok', False)

    @classmethod
    def __graph_request(cls, operation: dict):
        variables = operation.get('variables', {})
        if isinstance(variables, str):
            variables = json.loads(variables)
        ws_id = variables.get('workspaceId')

        matcher_url = settings.MATCHER_SERVICE_URL
        if ws_id and Workspace.objects.get(id=ws_id).config.get('is_custom', False):
            matcher_url = settings.MATCHER_SERVICE_V2_URL

        try:
            return requests.post(
                matcher_url + "/graphql",
                data=json.dumps(operation),
                headers={'Content-Type': 'application/json'},
                timeout=settings.SERVICE_TIMEOUT
            ).json()
        except requests.exceptions.Timeout:
            return {}
