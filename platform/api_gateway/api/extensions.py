from strawberry.types import Info
from strawberry.extensions import Extension
from promise import Promise
from django.contrib.auth.models import AnonymousUser
from api_gateway.api.token import Token
from user_domain.models import Access, Workspace
from platform_lib.utils import get_workspace_id, get_token, get_user
from plib.tracing.utils import get_tracer, ContextStub


class AuthorizationExtension(Extension):
    ingored_endpoints = ['me', '__schema']

    def resolve(self, _next, root, info: Info, *args, **kwargs) -> Promise:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("authorization_extension") if tracer else ContextStub() as span:
            if info.path.prev is not None:
                return _next(root, info, *args, **kwargs)

            user = get_user(info=info)

            if info.field_name in self.ingored_endpoints and not isinstance(user, AnonymousUser):
                return _next(root, info, *args, **kwargs)

            token = get_token(info=info)
            workspace_id = get_workspace_id(info=info)

            if token:
                if not workspace_id:
                    token = Token.from_string(token)
                    if token.is_access():
                        info.context.request.META['workspace_id'] = str(Workspace.objects.get(accesses__id=token.id).id)
                    if token.is_activation():
                        info.context.request.META['workspace_id'] = str(
                            Workspace.objects.get(agents__activations__id=token.id).id
                        )
                    if token.is_agent():
                        info.context.request.META['workspace_id'] = str(Workspace.objects.get(agents__id=token.id).id)
                return _next(root, info, *args, **kwargs)

            if workspace_id and not isinstance(user, AnonymousUser) and (workspace_id in [str(access.workspace.id)
                                                                         for access in user.accesses.all()]):
                if not token:
                    info.context.request.META['HTTP_TOKEN'] = str(Access.objects.get(workspace_id=str(workspace_id)).id)
                return _next(root, info, *args, **kwargs)
            else:
                raise PermissionError('Permission denied')


# TODO: Remove after frontend fix
class TriggerExtension(Extension):
    def on_request_start(self):
        if self.execution_context.query.find('createTrigger(') != -1 and self.execution_context.variables is not None:
            self.execution_context.variables['triggerData']['limit'] = int(self.execution_context.variables
                                                                           .get('triggerData', {}).get('limit'))
