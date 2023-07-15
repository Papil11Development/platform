from .consumers import NotificationConsumer
from .views import PostProcess, ActivationView, GetImage, GetAgentLink, ExternalLogin, GetNotifications,\
    GetRealtimeImage, DuplicatePerson

from django.urls import path, include
from django.conf import settings

from api_gateway.api.v1.schema import schema as schema_v1
from api_gateway.api.v1.internal_schema import schema as internal_schema_v1
from api_gateway.api.v2.schema import schema as schema_v2
from api_gateway.api.v2.internal_schema import schema as internal_schema_v2
from api_gateway.api.v3.schema import schema as schema_v3
from api_gateway.api.vlw.internal_schema import schema as internal_schema_vlw
from api_gateway.views import APIView


urlpatterns = [
    path('api/v1/', APIView.as_view(schema=schema_v1, graphiql=True, allow_queries_via_get=False)),
    path('api/v2/', APIView.as_view(schema=schema_v2, graphiql=True, allow_queries_via_get=False)),
    path('api/v3/', APIView.as_view(schema=schema_v3, graphiql=True, allow_queries_via_get=False)),
    path('internal-api/v1/', APIView.as_view(
        schema=internal_schema_v1, graphiql=settings.DEBUG, allow_queries_via_get=False)),
    path('internal-api/v2/', APIView.as_view(
        schema=internal_schema_v2, graphiql=settings.DEBUG, allow_queries_via_get=False)),
    path('internal-api/vlw/', APIView.as_view(schema=internal_schema_vlw, graphiql=settings.DEBUG)),
    path('internal-api/v2/external-login/', ExternalLogin.as_view()),
    path('rest-api/v1/post-event/', PostProcess.as_view()),
    path('rest-api/v1/activate/', ActivationView.as_view()),
    path('get-image/<sample_id>/', GetImage.as_view()),
    path('get-realtime-image/<image_key>/', GetRealtimeImage.as_view()),
    path('get-notification/', GetNotifications.as_view()),
    path('get-agent/v1/<os_version>/', GetAgentLink.as_view()),
    path('get-agent/v2/<os_version>/', GetAgentLink.as_view()),
    path('api/qa/duplicate-person/', DuplicatePerson.as_view()),
    path('licensing/', include('licensing.urls')),
]

websocket_urlpatterns = [
    path('ws/notifications/', NotificationConsumer.as_asgi()),
]
