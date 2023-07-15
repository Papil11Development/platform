import copy
import uuid
from collections import namedtuple
from typing import List, Dict, Union

PresenceResult = namedtuple('PresenceResult', ['result', 'target_info'])
LocationResult = namedtuple('LocationResult', ['result', 'current_count'])


class MetaLanguageParser:
    """
    A class that handles the meta language of triggers.
    The class allows you to get the required information from the language and calculate the trigger condition
    based on the following ongoings

    Parameters
    ----------
    meta: dict
        trigger meta language

    Methods
    -------
    get_variable_type_by_name(variable_name: str):
        Obtain the type of function required to calculate a variable from the variable name
    get_variable_type_by_number(variable_name: str):
        Obtain the type of function required to calculate a variable from the variable number
    calculate_meta_condition(ongoings: list):
        Checks the condition derived from the meta-language on the set of received ongoings
    """

    dict_types_places = {
        'camera': 'camera_id',
        'location': 'location_ids',
        'attention_area': 'attention_area_ids',
        'area_type': 'area_type_ids'
    }

    def __init__(self, meta: dict):
        self.meta = meta
        self.__func_call_dict, self.__condition = self.__parse_meta_language(copy.deepcopy(meta))

    def get_condition(self):
        return self.__condition

    def get_targets(self, variable_number: int) -> List[Dict]:
        return list(self.__func_call_dict.values())[variable_number][1].get("target", {})

    def get_places(self, variable_number: int) -> List[Dict]:
        return list(self.__func_call_dict.values())[variable_number][1].get("place", {})

    def get_profile_group_ids_from_variable(self, variable_number):
        return [target.get('uuid') for target in self.get_targets(variable_number) if target.get('type') == 'Label']

    def get_variable_type_by_name(self, variable_name: str) -> str:
        """
        Get function type by variable name

        Returns
        -------
        str:
            A string specifying which function to pass the variable's arguments to in order to calculate its value
        """
        return self.__func_call_dict[variable_name][0]

    def get_variable_type_by_number(self, variable_number: int) -> str:
        """
        Get function type by variable number

        Returns
        -------
        str:
            A string specifying which function to pass the variable's arguments to in order to calculate its value
        """
        return list(self.__func_call_dict.values())[variable_number][0]

    def get_variable_kwargs_by_number(self, variable_number: int) -> Dict:
        """
        Get function kwargs by variable number

        Returns
        -------
        str:
            Function kwargs
        """
        return list(self.__func_call_dict.values())[variable_number][1]

    def calculate_meta_condition(self, packed_ongoings: list, notification_score_threshold: float) -> tuple:
        """
        Calculate a condition written in meta language based on data from ongoings

        Parameters
        ----------
        packed_ongoings: list
            List of packed ongoings with information on finding people in locations
        notification_score_threshold: float
            Threshold for creating notifications by person presence

        Returns
        -------
        tuple
            1) Result of the condition.
            2) Dictionary with variable execution result.
        """
        if packed_ongoings is None:
            packed_ongoings = [{}]

        condition_variables_result = {}
        variable_function_mapping = self.__get_variable_function_mapping()

        for function_var_name, function_call in self.__func_call_dict.items():
            func_type = function_call[0]
            func_kwargs = function_call[1]
            # Enriching function named-arguments with ongoings
            func_kwargs["packed_ongoings"] = packed_ongoings
            func_kwargs["notification_score_threshold"] = notification_score_threshold

            condition_variables_result[function_var_name] = (variable_function_mapping[func_type](**func_kwargs))

        if self.__condition:
            # TODO made this when condition will be more than one variable
            pass
        else:
            # Return first variable result if no condition presented
            return list(condition_variables_result.values())[0].result, condition_variables_result

    @classmethod
    def __get_variable_function_mapping(cls) -> dict:
        return {
            "presence": cls.__presence,
            "location_overflow": cls.__location_overflow
        }

    def is_have_target(self, target_id: Union[str, uuid.UUID]) -> bool:
        for i, _ in enumerate(self.__func_call_dict):
            targets = self.get_targets(i)
            if str(target_id) in [target.get('uuid') for target in targets]:
                return True

        return False

    def is_have_place(self, place_id: Union[str, uuid.UUID]) -> bool:
        for i, _ in enumerate(self.__func_call_dict):
            places = self.get_places(i)
            if str(place_id) in [place.get('uuid') for place in places]:
                return True

        return False

    @staticmethod
    def __check_operation(check_count: int, operation: str, limit: int) -> bool:

        if type(check_count) != int or type(limit) != int:
            return False

        acceptable_operations = ['>', '<', '=', '<=', '>=', '!=']
        if operation in acceptable_operations:
            eval_expression = f'{check_count} {operation} {limit}'
            return eval(eval_expression)
        else:
            return False

    @staticmethod
    def __parse_meta_language(trigger_condition: dict) -> tuple:
        variables = trigger_condition.get("variables")
        condition = trigger_condition.get("condition")

        function_call_dict = {}

        for variable_name, variable_args in variables.items():
            func_type = variable_args.pop("type")
            func_kwargs = variable_args
            function_call_dict[variable_name] = (func_type, func_kwargs)

        return function_call_dict, condition

    @classmethod
    def __location_overflow(cls, **kwargs) -> LocationResult:
        """
        Function that determines that there are more people in a given place than the limit

        Examples
        --------
        On cash register is more than 10 people
        """
        packed_ongoings = kwargs["packed_ongoings"]
        target_operation = kwargs["target_operation"]
        target_limit = kwargs["target_limit"]
        places = kwargs["place"]

        place_uuids = {place["uuid"] for place in places}

        variable_result = False
        current_count = 0

        for ongoing in packed_ongoings:
            if set(ongoing["location_ids"]) & place_uuids:
                current_count = len(ongoing["persons"])
                if cls.__check_operation(check_count=current_count,
                                         operation=target_operation,
                                         limit=target_limit):
                    variable_result = True
                    break

        return LocationResult(variable_result, current_count)

    @classmethod
    def __presence(cls, **kwargs) -> PresenceResult:
        """
        Function that determines whether a target is present or absent in any area of camera coverage in any quantity

        Examples
        --------
        VIP is exist in any place
        """
        packed_ongoings = kwargs["packed_ongoings"]
        target_operation = kwargs["target_operation"]
        target_limit = kwargs["target_limit"]
        targets = kwargs["target"]
        notification_score_threshold = kwargs['notification_score_threshold']

        target_uuids = [target["uuid"] for target in targets]
        detected_targets = []

        for ongoing in packed_ongoings:
            location_id = ongoing["location_ids"][0]
            for person in ongoing['persons']:
                if person.get('match_data', {}).get('score', 1) < notification_score_threshold:
                    continue
                person_id = person["id"]
                # profile may not exist if person is not exist in base
                profile_id = person.get("profile_id")
                person_labels = person["profile_group_ids"]

                person_info = {
                    "id": person_id,
                    "profile_id": profile_id,
                    'activity_id': person['activity_id'],
                    # "have_face_best_shot": person["have_face_best_shot"],
                    # "have_body_best_shot": person["have_body_best_shot"],
                    "face_best_shot": person["face_best_shot"],
                    "body_best_shot": person["body_best_shot"],
                    "profile_group_ids": person_labels,
                    "location_id": location_id,
                    "camera_id": ongoing["camera_id"],
                }

                if person_id in target_uuids:
                    detected_targets.append(person_info)

                if set(person_labels) & set(target_uuids):
                    detected_targets.append(person_info)

        result = cls.__check_operation(check_count=len(detected_targets),
                                       operation=target_operation,
                                       limit=target_limit)

        return PresenceResult(result, detected_targets)
