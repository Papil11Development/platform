import uuid
from django.db import models
from platform_lib.utils import utcnow_with_tz
from collector_domain.models import Agent


class Activation(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    signature = models.JSONField(default=dict)
    creation_date = models.DateTimeField(default=utcnow_with_tz)
    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    previous_activation = models.ForeignKey(
        'self', on_delete=models.CASCADE, related_name='next_activation', null=True, blank=True)
    agent = models.ForeignKey(to=Agent, on_delete=models.CASCADE, related_name='activations')

    @property
    def token(self):
        return str(self.id)

    @property
    def is_manual(self):
        return self.previous_activation is None

    class Meta:
        db_table = 'agent_activation'


def find_last_activation(activations, _id):
    activation = activations[0]
    if activation.is_manual:
        if activation.id != uuid.UUID(_id):
            return None

        return activation

    elif activation.id == uuid.UUID(_id):
        return activation

    elif activation.previous_activation.id == uuid.UUID(_id):
        return activation.previous_activation

    return None
