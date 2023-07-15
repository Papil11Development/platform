import json

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode

from main import settings
from platform_lib.utils import database_sync_to_async
from user_domain.models import Workspace
from plib.tracing import ConnectionManager


class WorkspaceAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        workspace_id = scope['cookies'].get('workspace')
        user = scope['user']
        if not isinstance(user, AnonymousUser):
            try:
                await database_sync_to_async(lambda: Workspace.objects.get(id=workspace_id,
                                                                           accesses__user=user,
                                                                           config__is_active=True))()
            except (Workspace.DoesNotExist, ValidationError):
                scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)


class TraceMiddleware:
    def __init__(self, get_response):
        self.tracer = ConnectionManager.init_connection(settings.SERVICE_NAME, settings.TRACER_URL)
        self.get_response = get_response

    def __call__(self, request):
        with self.tracer.start_as_current_span(request.path) as span:
            span.set_attribute(SpanAttributes.HTTP_METHOD, request.method)
            span.set_attribute(SpanAttributes.HTTP_URL, request.get_full_path())

            response = self.get_response(request)
            span.set_attribute(SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH, len(response.content))

            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            elif isinstance(response, JsonResponse):
                body_unicode = response.content.decode('utf-8')
                body_data = json.loads(body_unicode)

                if (error := body_data.get("errors", [None])[0]) is not None:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(Exception(error))

            span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, response.status_code)

        return response
