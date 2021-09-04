import base64
import json


from django.conf import settings
from django.http import JsonResponse

from .certificate import generate_certificate, SignatureToolError
from api_gateway.api.token import InvalidToken, EmptyToken
from platform_lib.exceptions import InvalidJsonRequest, InvalidSignature, AgentIsBlocked, TokenExpired, \
    InvalidClientTimestamp, WorkspaceInactive, TemplateValidationError


def encode_license(license_str: str):
    return base64.b64encode(license_str.encode()).decode()


def catch_exception(func):
    def return_error(status, error: str):
        license_data = encode_license(json.dumps({'Error': str(error)}))

        data = {
            'License': license_data,
            'Certificate': generate_certificate(license_data, settings.PRIVATE_KEY_RESPONSE,
                                                settings.PUBLIC_KEY_RESPONSE,
                                                settings.LICENSE_SIGNATURE_TOOL)
        }

        return JsonResponse(data=data, status=status)

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (InvalidToken, TokenExpired, InvalidSignature, InvalidJsonRequest, SignatureToolError, AgentIsBlocked,
                InvalidClientTimestamp, WorkspaceInactive, TemplateValidationError, EmptyToken) as ex:
            return return_error(400, str(ex))
        except Exception as ex:
            return return_error(500, str(ex))

    return wrapper
