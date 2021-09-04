# -*- coding: utf-8 -*-
from jsonschema import Draft202012Validator, draft202012_format_checker, ValidationError


def is_valid_json(_dict, schema):
    try:
        Draft202012Validator(schema, format_checker=draft202012_format_checker).validate(_dict)
        return True
    except ValidationError as ex:  # TODO hard to debug need to make it verbose
        return False
