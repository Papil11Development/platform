import json
import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User


class LicenseServerAuth:
    def authenticate(self, request, username=None, password=None):
        try:
            user = User.objects.get(username=username)
        except ObjectDoesNotExist as ex:
            return None

        auth_success, message = self.__authenticate_at_license_server(username, password)

        if not auth_success:
            return None
        user.backend = 'api_gateway.auth_backends.LicenseServerAuth'
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except ObjectDoesNotExist:
            return None

    @classmethod
    def __authenticate_at_license_server(cls, username, password):
        response = requests.post(
            settings.EXTERNAL_AUTH_URL,
            data=json.dumps({'username': username, 'password': password, 'service': settings.LICENSING_PRODUCT_NAME}),
            headers={'Content-Type': 'application/json'})

        if response.status_code not in [200]:
            if response.headers['Content-Type'] == 'application/json':
                return False, json.loads(response.content).get('error')
            else:
                return False, 'Unexpected content type'
        else:
            return True, 'ok'
