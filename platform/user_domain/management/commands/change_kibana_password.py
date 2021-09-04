from django.core.management import BaseCommand
from django.db import transaction
from main import settings
import json
import requests

from user_domain.models import User, Workspace
from user_domain.api.utils import get_kibana_password


def get_kibana_user(username: str):
    url = f'{settings.ELASTIC_URL_EXT}/_security/user/{username}'
    return requests.get(url, headers=settings.ELASTIC_HEADERS_EXT).json()


def change_password(username, password):
    url = f'{settings.ELASTIC_URL_EXT}/_security/user/{username}/_password'
    data = {'password': password}
    return requests.post(url, data=json.dumps(data), headers=settings.ELASTIC_HEADERS_EXT).content


class Command(BaseCommand):
    def handle(self, *args, **options):
        for user in User.objects.all():
            password = get_kibana_password(user)
            if password is None:
                if get_kibana_user(user.username):
                    password = User.objects.make_random_password()
                else:
                    continue

            with transaction.atomic():
                response_content = change_password(user.username, password)
                if b'error' in response_content:
                    print(f'Exception has occurred: {response_content}. For workspace {str(access.workspace.id)}')
                    continue

                for access in user.accesses.all():
                    locked_ws = Workspace.objects.get(id=access.workspace.id)
                    locked_ws.config.update({'kibana_password': password})
                    locked_ws.save()
