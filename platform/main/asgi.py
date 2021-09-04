"""
ASGI config for main project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

from django.core.asgi import get_asgi_application


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django_asgi_app = get_asgi_application()

import api_gateway.urls  # noqa
from api_gateway.middleware import WorkspaceAuthMiddleware  # noqa

asgi_routes = dict()
asgi_routes["http"] = django_asgi_app
asgi_routes["websocket"] = AuthMiddlewareStack(WorkspaceAuthMiddleware(
        URLRouter(
            api_gateway.urls.websocket_urlpatterns
        )
    )
)

application = ProtocolTypeRouter(asgi_routes)
