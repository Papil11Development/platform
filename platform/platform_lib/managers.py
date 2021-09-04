import base64
import uuid
from typing import Optional, Dict, List, Union, Tuple, Callable
from enum import Enum
import bson
import jsonschema

import requests
import json
from django.core.cache import cache

from platform_lib.exceptions import KibanaError
from platform_lib.validation.schemes import trigger_meta_scheme, sample_meta_scheme


class BaseProcessManager:
    """
    A class with basic methods for working with processes
    """
    class ProcessClass(str, Enum):
        FACE = "face"
        BODY = "body"
        HUMAN = "human"
        ROI = "roi"
        MEDIA = "media"

    bsm_indicator = "$"

    key_process_info_values = {'quality', 'age', 'gender', 'time_interval', 'finalized', 'class'}

    def __init__(self, processes: List[Dict]):
        self.processes = processes

        # For static method replacing
        self._get_processes = self._get_processes_instance

    @staticmethod
    def _get_processes(process_class: ProcessClass, processes: List[Dict]) -> List[Dict]:
        """
        Get all processes witch class is **process_class**
        Parameters
        ----------
        process_class: ProcessClass
            Process class that defines witch processes is need to be obtained.  Search in **processes**
        processes: List[Dict]:
            List of processes to search in
        Returns
        -------
        List[Dict]
            List of process with process_class
        """
        return list(filter(lambda track: track.get('object', {}).get('class') == process_class.value, processes))

    def _get_processes_instance(self, process_class: ProcessClass) -> List[Dict]:
        """
        Get all processes witch class is **process_class**. Search in **self.processes**
        Parameters
        ----------
        process_class: ProcessClass
            Process class that defines witch processes is need to be obtained
        Returns
        -------
        List[Dict]
            List of process with process_class
        """
        return list(filter(lambda track: track.get('object', {}).get('class') == process_class.value, self.processes))

    @classmethod
    def _iterate_through_process(cls,
                                 process: Dict,
                                 function: Callable,
                                 function_extra: Optional[Dict] = None,
                                 only_bsm: Optional[bool] = False):
        """
        Function that goes through process dict by recursion and call **function** if key of **process** element
        is bsm or located in **key_process_info_values**. All

        Parameters
        ----------
        process: Dict
            Process dict
        function: Callable
            Function that called at elements that start with bsm_indicator
            or located in key_process_info_values.
            Function arguments: key: dict key; value: dict value; process: dict element that iterated now;
            and all kwargs from function_extra if passed
        function_extra: Optional[Dict]
            Additional function arguments
        only_bsm: Optional[False]
            Call function only on keys that start with bsm_indicator
        """
        if isinstance(process, dict):
            for key, value in process.items():
                if key.startswith(cls.bsm_indicator) or (not only_bsm and (key in cls.key_process_info_values)):
                    function(key, value, process, **(function_extra or {}))
                else:
                    cls._iterate_through_process(value, function, function_extra, only_bsm)

        elif isinstance(process, list):
            for value in process:
                cls._iterate_through_process(value, function, function_extra, only_bsm)

    @classmethod
    def get_process_info(cls, process: Dict) -> Dict:
        """
        Get all process info, namely fields that start with **bsm_indicator**
        and fields that keys located in **key_process_info_values**

        Parameters
        ----------
        process: Dict
            Process information in dictionary

        Returns
        -------
        Dict:
            Dictionary with obtained data
        """
        process_info = {}

        def function(key, value, _, result_variable):
            result_variable[key] = value

        cls._iterate_through_process(process, function, function_extra={"result_variable": process_info})

        return process_info

    @classmethod
    def get_process_class(cls, process: Dict) -> Optional[ProcessClass]:
        """
        Get process class

        Parameters
        ----------
        process: Dict
            Process information in dictionary

        Returns
        -------
        ProcessClass:
            Process class representation
        """
        process_class = process.get('object', {}).get('class')

        return cls.ProcessClass(process_class) if process_class is not None else None

    @classmethod
    def is_process_finalized(cls, process: Dict) -> bool:
        """
        Defines if process finalized or not by checking finalized field in process data

        Parameters
        ----------
        process: Dict
            Process dict witch need to checked

        Returns
        -------
        bool:
            Process finalized or not
        """
        return process.get('finalized', True)

    @classmethod
    def get_process_timeinterval(cls, process: Dict) -> Tuple[int, int]:
        """
        Get process time interval

        Parameters
        ----------
        process: Dict
            Process information in dictionary

        Returns
        -------
        Tuple[int, int]
            List of two values. First is start time, second is end time.
        """
        timeinterval = process.get('time_interval')

        return timeinterval[0], timeinterval[1]

    @classmethod
    def is_media_process(cls, processes: List[Dict]) -> bool:
        """
        Defines if list of process contains media process or not
        Parameters
        ----------
        processes: List[Dict]
            List of process that need to be checked

        Returns
        -------
        bool:
            List of process have media or not
        """
        media = cls._get_processes(cls.ProcessClass.MEDIA, processes)
        return bool(media)

    def get_human_processes(self) -> List[Dict]:
        """
        Get all human processes

        Returns
        -------
        List[Dict]:
            List of human processes in dictionaries
        """
        return self._get_processes(self.ProcessClass.HUMAN)

    def get_face_processes(self) -> List[Dict]:
        """
        Get all face processes

        Returns
        -------
        List[Dict]:
            List of face processes in dictionaries
        """
        return self._get_processes(self.ProcessClass.FACE)

    def get_body_processes(self) -> List[Dict]:
        """
        Get all body processes

        Returns
        -------
        List[Dict]:
            List of body processes in dictionaries
        """
        return self._get_processes(self.ProcessClass.BODY)

    def get_roi_process(self) -> List[Dict]:
        """
        Get all roi processes

        Returns
        -------
        List[Dict]:
            List of roi processes in dictionaries
        """
        return self._get_processes(self.ProcessClass.ROI)


class RawProcessManager(BaseProcessManager):

    @classmethod
    def validate_sample_meta(cls, meta: Dict) -> bool:

        def json_decoder(o: Union[list, tuple, str]):
            if isinstance(o, str):
                try:
                    return int(o)
                except ValueError:
                    try:
                        return float(o)
                    except ValueError:
                        return o
            elif isinstance(o, dict):
                return {k: json_decoder(v) for k, v in o.items()}
            elif isinstance(o, (list, tuple)):
                return type(o)([json_decoder(v) for v in o])
            else:
                return o

        try:
            jsonschema.validate(meta, sample_meta_scheme)
        except jsonschema.ValidationError:
            try:
                # bson doesn't decode numbers therefore try to decode meta data
                s = {k: json_decoder(v) for k, v in meta.items()}
                jsonschema.validate(s, sample_meta_scheme)
            except Exception:
                return False
        return True

    @classmethod
    def __bsm(cls, key: str, blob: bytes) -> Dict:
        return {
            f'{cls.bsm_indicator}{key}': {
                'format': 'IMAGE',
                'blob': blob
            }
        }

    @classmethod
    def parse_extra(cls, data: Dict) -> Dict:
        result = {k: v for k, v in data.items() if k not in ['prediction']}
        prediction = json.loads(data.get('prediction', '{}'))
        if 'objects' in prediction:
            result['objects'] = prediction['objects']
        return result

    @classmethod
    def decode(cls, data: bytes) -> Tuple[Dict, bool]:
        """
        Decodes abstract sample got over network

        Parameters
        ----------
        data: bytes
            "network sample" or raw_image

        Returns
        -------
        Tuple[Dict, bool]:
            decoded sample and flag that specifies is input was a raw image or "network sample"
        """
        version_size = 1
        version = int.from_bytes(data[:version_size], byteorder='big')
        if version == 1:
            return bson.loads(data[version_size:]), False

        # assume that it is a raw image and pack it to bsm format
        return cls.__bsm('image', data), True

    @classmethod
    def parse_human_processes(cls, processes: List[Dict]) -> List[Dict]:
        humans = cls._get_processes(cls.ProcessClass.HUMAN, processes)
        humans_pack = []

        def get_child(parent_id: str, output: list):
            for proc in processes:
                if proc.get('parent') == parent_id:
                    output.append(proc)
                    get_child(proc['id'], output)

        for human in humans:
            if human.get('finalize', True) and not human.get('object', {}).get('id'):
                continue
            res = [human]
            get_child(human['id'], res)
            humans_pack.append({'processes': res})

        return humans_pack

    @classmethod
    def extract_bsms(cls, meta: Dict) -> Tuple[Dict, List[Tuple]]:
        bsms = []

        def function(key, value, element, result_value):
            result_value.append((key, value, str(uuid.uuid4())))
            element[key] = len(result_value) - 1

        cls._iterate_through_process(meta, function, function_extra={"result_value": bsms}, only_bsm=True)

        return meta, bsms

    @classmethod
    def substitute_bsms(cls, meta: Dict, bsms: List) -> Dict:

        def function(key, value, element, bsms):
            element[key] = bsms[value]

        cls._iterate_through_process(meta, function, function_extra={"bsms": bsms}, only_bsm=True)

        return meta


class ActivityProcessManager(BaseProcessManager):

    @classmethod
    def _get_blob_ids(cls, process: Dict) -> List[str]:
        blob_ids = []

        def function(key, value, element, result_value):
            result_value.append(value["id"])

        cls._iterate_through_process(process, function, function_extra={"result_value": blob_ids}, only_bsm=True)

        return blob_ids

    def __init__(self, activity_data: Dict):
        activity_processes = activity_data['processes']
        super().__init__(activity_processes)
        assert len(self.get_human_processes()) == 1, "Wrong activity. To many human processes"

    def get_age_gender(self) -> Tuple[Optional[int], Optional[str]]:
        face_processes = self.get_face_processes()
        if len(face_processes) == 0:
            return None, None

        face_info = self.get_process_info(face_processes[0])

        return face_info.get('age'), face_info.get('gender')

    def get_face_best_shot(self) -> Optional[Dict]:
        face_processes = self.get_face_processes()
        if len(face_processes) == 0:
            return None

        face_info = self.get_process_info(face_processes[0])

        return face_info.get('$best_shot')

    def get_body_best_shot(self) -> Optional[Dict]:
        body_processes = self.get_body_processes()
        if len(body_processes) == 0:
            return None

        body_info = self.get_process_info(body_processes[0])

        return body_info.get('$best_shot')

    def get_human_process(self) -> Dict:
        return self.get_human_processes()[0]

    def is_activity_finalized(self) -> bool:
        human = self.get_human_process()

        return self.is_process_finalized(human)

    def get_human_timeinterval(self) -> Tuple[int, int]:
        return self.get_process_timeinterval(self.get_human_process())

    def get_person_id(self) -> Optional[str]:
        return self.get_human_process().get('object', {}).get('id')

    def get_activity_blob_ids(self) -> List[str]:
        blob_ids = []
        for process in self.processes:
            blob_ids += self._get_blob_ids(process)

        return blob_ids


class TriggerMetaManager:
    """
    Class that help generate trigger condition meta language and notification default params
    """

    def __init__(self, meta: Optional[Dict] = None):

        if meta is None:
            meta = {}

        self.__schema = trigger_meta_scheme
        self.__variable_format = "{}_v"
        self.__variable_numerator = len(meta.get('condition_language', {}).get('variables', []))
        self.__notification_params = meta.get('notification_params', {})
        self.__condition_language = meta.get('condition_language', {"variables": {}})

        self.__meta = meta or {
            "notification_params": self.__notification_params,
            "condition_language": self.__condition_language
        }

    def get_condition_language(self):
        return self.__condition_language

    def get_notification_params(self):
        return self.__notification_params

    def get_variable_name(self) -> str:
        """
        Generate variable name from variable_numerator var that starts from 0 when class is initialize.
        Variable_numerator increase at 1 every method call

        Returns
        -------
        str
            Represent variable name
        """
        variable = self.__variable_format.format(self.__variable_numerator)
        self.__variable_numerator += 1
        return variable

    # TODO get type right
    @staticmethod
    def __get_place_pack(places_list) -> List[Dict]:
        """
        Get packed info from database objects that represents condition places.
        Info format: { "type": "place class name", "uuid": "place id in string" }

        Parameters
        ----------
        places_list:
            List of database objects that represents condition places

        Returns
        -------
        List[Dict]
            List of packed place info
        """
        place_pack = []
        for place in places_list:
            place_pack.append({
                "type": place.__class__.__qualname__,
                "uuid": str(place.id)
            })
        return place_pack

    # TODO get type right
    @staticmethod
    def __get_target_pack(target_list: List):
        """
        Get packed info from database objects that represents condition targets.
        Info format: { "type": "target class name", "uuid": "target id in string" }

        Parameters
        ----------
        target_list:
            List of database objects that represents condition targets

        Returns
        -------
        List[Dict]
            List of packed target info in this format:
        """
        target_pack = []
        for target in target_list:
            target_pack.append({
                "type": target.__class__.__qualname__,
                "uuid": str(target.id)
            })
        return target_pack

    def add_location_overflow_variable(self,
                                       place_list: List,
                                       target_limit: int,
                                       target_operation: str):
        """
        Append location overflow type variable to condition meta

        Parameters
        ----------
        place_list:
            List of database objects that represents place targets
        target_operation: str
            Sign of the arithmetic operation, such as >, >=
        target_limit: str
            Number that represent edge count

        Returns
        -------
        TriggerMetaGenerator
        """
        self.__condition_language["variables"][self.get_variable_name()] = {
            "type": "location_overflow",
            "place": self.__get_place_pack(place_list),
            "target_limit": target_limit,
            "target_operation": target_operation
        }
        return self

    def add_presence_variable(self,
                              target_list: List,
                              target_limit: int,
                              target_operation: str):
        """
        Append presence type variable to condition meta

        Parameters
        ----------
        target_list:
            List of database objects that represents condition targets
        target_operation: str
            Sign of the arithmetic operation, such as >, >=
        target_limit: str
            Number that represent edge count

        Returns
        -------
        TriggerMetaGenerator
        """
        self.__condition_language["variables"][self.get_variable_name()] = {
            "type": "presence",
            "target": self.__get_target_pack(target_list),
            "target_limit": target_limit,
            "target_operation": target_operation
        }
        return self

    def update_notification_params(self, param_input: Optional[Dict] = None):
        self.__notification_params.update(param_input or {})
        return self

    def get_trigger_lifetime(self) -> Optional[int]:
        return self.get_notification_params().get('lifetime')

    def get_meta(self):
        return self.__meta


class KibanaManager:
    def __init__(self, kibana_url, headers):
        self.url = kibana_url
        self.headers = headers

    def create_space(self, space_id, title):
        params = {'id': space_id, 'name': title}
        return requests.post(f'{self.url}/api/spaces/space', headers=self.headers, data=json.dumps(params)).json()

    def get_space(self, space_id):
        return requests.get(f'{self.url}/api/spaces/space/{space_id}', headers=self.headers).json()

    def get_spaces(self):
        return requests.get(f'{self.url}/api/spaces/space', headers=self.headers).json()

    def delete_space(self, space_id):
        response = requests.delete(f'{self.url}/api/spaces/space/{space_id}', headers=self.headers)
        if 'error' in str(response.content):
            raise Exception(response.json().get('error'))

    def change_space_settings(self, index_id, space_id):
        url = f'{self.url}/s/{space_id}/api/kibana/settings'
        new_settings = [
            {"changes": {"defaultIndex": index_id}},
            {"changes": {"timepicker:refreshIntervalDefaults": "{\n  \"pause\":false,\n  \"value\":60000\n}"}},
            {"changes": {"timepicker:timeDefaults": "{\n  \"from\": \"now-30d/d\",\n  \"to\": \"now\"\n}"}}
        ]

        for data in new_settings:
            requests.post(url, headers=self.headers, data=json.dumps(data))

    def create_index_pattern(self, index_id, pattern_data, id_space):
        url = f'{self.url}/s/{id_space}/api/saved_objects/index-pattern/{index_id}'
        pattern_data['attributes']['title'] = index_id
        return requests.post(url, headers=self.headers, data=json.dumps(pattern_data)).json()

    def get_saved_objects(self, space_id, object_type):
        if object_type not in ['index-pattern', 'dashboard']:
            raise Exception('Unsupported object type.')
        url = f'{self.url}/s/{space_id}/api/saved_objects/_find?type={object_type}'
        return requests.get(url, headers=self.headers).json()

    def export_dashboard(self, id_export):
        url = f'{self.url}/api/kibana/dashboards/export?dashboard={id_export}'
        response = requests.get(url, headers=self.headers).json()
        if response.get('objects')[0].get('error'):
            raise KibanaError(response.get('objects')[0].get('error', {}).get('message'))
        return response

    def import_dashboard(self, data, id_space, pattern_id, title, dashboard_id):
        data = dict(data)
        url = f'{self.url}/s/{id_space}/api/kibana/dashboards/import?exclude=index-pattern'
        data['objects'][0]['id'] = dashboard_id
        data['objects'][0]['attributes']['title'] = title
        new_ref = json.loads(data['objects'][0]['attributes']['panelsJSON'])
        for elem in new_ref:
            if elem['embeddableConfig'].get('savedVis'):
                continue
            else:
                for elem_id in elem['embeddableConfig']['attributes']['references']:
                    elem_id['id'] = pattern_id
        data['objects'][0]['attributes']['panelsJSON'] = json.dumps(new_ref)
        for number in data['objects'][0]['references']:
            number['id'] = pattern_id
        return requests.post(url, headers=self.headers, data=json.dumps(data)).json()

    def get_role(self, role):
        return requests.get(f'{self.url}/api/security/role/{role}', headers=self.headers).json()

    def delete_role(self, role):
        response = requests.delete(f'{self.url}/api/security/role/{role}', headers=self.headers)
        if 'error' in str(response.content):
            raise Exception(response.json().get('error'))

    def change_role_spaces(self, role, old_space_id, new_space_id):
        all_perms = self.get_role(role)
        kibana_perms = all_perms['kibana']
        elasticsearch_perms = all_perms['elasticsearch']
        url = f'{self.url}/api/security/role/{role}'
        for perm in kibana_perms:
            try:
                perm['spaces'].remove(old_space_id)
                perm['spaces'].append(new_space_id)
            except ValueError:
                pass
        data = json.dumps({'elasticsearch': elasticsearch_perms, 'kibana': kibana_perms})
        response = requests.put(url, data=data, headers=self.headers)
        if 'error' in str(response.content):
            raise Exception(response.json().get('error'))

    def get_roles_by_space(self, space_id):
        roles = requests.get(f'{self.url}/api/security/role', headers=self.headers).json()
        return [r['name'] for r in roles for perm in r['kibana'] if space_id in perm['spaces']]


class RealtimeImageCacheManager:
    rlt_face_key_format = "rlt_face_image_{}"
    rlt_body_key_format = "rlt_body_image_{}"

    @classmethod
    def get_profile_id_from_key(cls, rlt_key: str) -> str:
        split_mass = rlt_key.split('_')
        return split_mass[len(split_mass) - 1]

    @classmethod
    def get_realtime_keys(cls, profile_id: Union[str, uuid.UUID]) -> Tuple[str, str]:
        return cls.rlt_face_key_format.format(profile_id), cls.rlt_body_key_format.format(profile_id)

    @classmethod
    def set_realtime_image_cache(cls, profile_id: Union[str, uuid.UUID], face_image, body_image):
        cls.__set_image_in_cache(cls.rlt_face_key_format.format(profile_id), face_image)
        cls.__set_image_in_cache(cls.rlt_body_key_format.format(profile_id), body_image)

    @staticmethod
    def __set_image_in_cache(key: str, image: bytes) -> None:
        cache.set(key, image)

    @staticmethod
    def get_image_from_cache(key: str) -> bytes:
        return cache.get(key)
