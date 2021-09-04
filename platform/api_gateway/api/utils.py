import os
import json
from typing import Optional

from http.cookies import SimpleCookie

from platform_lib.utils import get_token, ApiError

from django.conf import settings
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.http import HttpResponseBadRequest, HttpResponse

from api_gateway.api.token import Token, InvalidToken, EmptyToken

from user_domain.models import Workspace, Access
from collector_domain.models import Agent
from activation_manager.models import Activation, find_last_activation


def get_access(qa_only=False):
    def decorator(func):
        def wrapper(request, *args, **kwargs):

            access_id = request.META.get('HTTP_TOKEN')
            if access_id is None:
                return HttpResponseBadRequest(json.dumps({'errors': 'Token header should be provided.'}))
            try:
                access = Access.objects.get(id=access_id, workspace__config__is_active=True)
            except (Access.DoesNotExist, ValidationError):
                return HttpResponseBadRequest(json.dumps({'errors': 'Access does not exist.'}))

            if qa_only and not access.user.groups.filter(name=settings.QA_GROUP).exists():
                return HttpResponseBadRequest(json.dumps({'errors': 'User not in a QA group.'}))

            return func(request, *args, access=access, **kwargs)
        return wrapper
    return decorator


def cors_resolver(func):
    def wrapper(request, *args, **kwargs):
        headers = set(
            h.strip().lower() for h in request.META.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', str()).split(','))
        origin = request.META.get('HTTP_ORIGIN')
        if request.method == 'OPTIONS' and 'token' in headers and origin is not None:
            response = HttpResponse()
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Methods'] = 'GET, POST'
            response['Access-Control-Allow-Headers'] = 'TOKEN, Content-Type'
            return response

        response = func(request, *args, **kwargs)
        if origin is not None:
            response['Access-Control-Allow-Origin'] = origin
        return response

    return wrapper


def check_activation_renewal(token):
    try:
        activation = Activation.objects.get(id=token.id)
    except ObjectDoesNotExist:
        return False

    activations = Agent.objects.get(activations=activation).activations.order_by('-creation_date')

    return find_last_activation(activations, token.id) is not None


def authorization(perm=None):
    perm = perm or []

    def decorator(func):
        def wrapper(request, *args, **kwargs):
            try:
                token = Token.from_string(request.META.get('HTTP_TOKEN'))
            except (InvalidToken, EmptyToken):
                return HttpResponseBadRequest(json.dumps({'errors': 'Wrong token.'}))

            if token.is_activation() and ('agent' not in perm or not check_activation_renewal(token)):
                return HttpResponseBadRequest(json.dumps({'errors': 'Wrong token.'}))
            elif (token.is_agent() or token.is_access()) and token.type not in perm:
                return HttpResponseBadRequest(json.dumps({'errors': 'You are not authorized.'}))

            workspace = get_workspace(token)

            return func(request, *args, workspace=workspace, token=token, **kwargs)

        return wrapper

    return decorator


def check_workspace(func):
    def wrapper(request, *args, **kwargs):
        workspace = kwargs.get('workspace', None)

        if workspace is None or not workspace.config.get('is_active', False):
            return HttpResponseBadRequest(json.dumps({'errors': 'Workspace is deactivated.'}))

        return func(request, *args, **kwargs)

    return wrapper


def set_cookies(cookie_str, response):
    def modify_param(param_name, param_value):
        # Removing the extra symbols, that are accidentally get in path
        if param_name == 'path' and isinstance(param_value, str):
            return param_value.replace(',', '')
        else:
            return param_value

    params = ['max_age', 'expires', 'domain', 'secure', 'httponly', 'samesite']
    parsed_cookies = SimpleCookie()
    parsed_cookies.load(cookie_str)

    for name, cookie in parsed_cookies.items():
        response.set_cookie(name, cookie.value, **{p: modify_param(p, cookie[p]) for p in params if p in cookie},
                            path='/')

    return response


def agent_from_activation_token(token: Token):
    return Agent.objects.get(activations=Activation.objects.get(id=token.id))


def get_workspace(token: Token) -> Optional[Workspace]:
    try:
        return {
            'access': lambda: Access.objects.get(id=token.id).workspace,
            'agent': lambda: Agent.objects.get(id=token.id).workspace,
            'activation': lambda: agent_from_activation_token(token).workspace
        }[token.type]()
    except ObjectDoesNotExist:
        return None


def validate_workspace(workspace: Workspace):
    if workspace is None:
        raise ApiError(message='Workspace is deactivated', error_code=ApiError.WORKSPACE_NOT_FOUND)
