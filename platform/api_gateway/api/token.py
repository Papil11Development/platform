from uuid import UUID

from django.conf import settings

from platform_lib.exceptions import InvalidToken, EmptyToken


class Token:
    valid_types = ['access', 'agent', 'service', 'activation', 'task']

    def __init__(self, _type: str, _id: str):
        self.type = _type.lower()
        self.id = _id

    def __str__(self):
        return self.id

    def __eq__(self, other):
        return self.type == other.type and self.id == other.id

    def is_access(self):
        return self.type == 'access'

    def is_agent(self):
        return self.type == 'agent'

    def is_service(self):
        return self.type == 'service'

    def is_activation(self):
        return self.type == 'activation'

    @classmethod
    def from_string(cls, uuid: str):
        from activation_manager.models import Activation
        from user_domain.models import Access
        from collector_domain.models import Agent

        if uuid == '':
            raise EmptyToken()

        if uuid == settings.SERVICE_KEY:
            return Token('service', uuid)

        if uuid is None:
            raise InvalidToken()

        try:
            UUID(uuid, version=4)
        except ValueError:
            raise InvalidToken()

        models = [
            ('activation', Activation),
            ('access', Access),
            ('agent', Agent)
        ]

        for name, model in models:
            if model.objects.filter(id=uuid).exists():
                return Token(name, uuid)

        raise InvalidToken()
