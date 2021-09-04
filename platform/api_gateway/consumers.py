import json

from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser


class NotificationConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_id = None

    async def connect(self):
        if isinstance(self.scope['user'], AnonymousUser):
            await self.close()
        else:
            self.workspace_id = self.scope['cookies']['workspace']

            await self.channel_layer.group_add(
                self.workspace_id,
                self.channel_name
            )

            await self.accept()

    async def disconnect(self, close_code):
        if self.workspace_id:
            await self.channel_layer.group_discard(
                self.workspace_id,
                self.channel_name
            )

    async def send_notifications(self, event):
        def to_camel_case(snake_str):
            components = snake_str.split('_')
            return components[0] + ''.join(x.title() for x in components[1:])

        event_dict_camel = {to_camel_case(key): value for key, value in event['info'].items()}

        await self.send(text_data=json.dumps(event_dict_camel))
