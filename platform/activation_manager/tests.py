import base64
import json
import os
from django.test import TestCase
from django.conf import settings as st
from datetime import datetime
from .models import Activation
from .certificate import generate_certificate, validate_certificate
from profile_manage.models import Device, Workspace
from facemachine.models import WorkspaceProperties
from api.utils import DummyValue
from storage_engine.settings import DEFAULT_TEMPLATES_VERSION


def data_encode(data):
    sign = data['Signature']

    data['Timestamp'] = str(datetime.utcnow().timestamp())
    data['Product'] = {'ID': 'qwe', 'Version': 'qwe'}
    data['OS'] = {'Name': '', 'Version': '', 'Architecture': ''}
    data['Environment'] = {}  # Network
    data['Sensor1'] = {'Type': '', 'Serial': '', 'Name': ''}
    data['Sensor2'] = {'Type': '', 'Serial': '', 'Name': ''}
    data['Sensors'] = [{'$ref': '#/Sensor1'}, {'$ref': '#/Sensor2'}]
    data['Device'] = {
        'Signature': {'$ref': '#Signature'},
        'Environment': {'$ref': '#/Environment'},
        'OS': {'$ref': '#OS'},
        'Sensors': {'$ref': '#Sensors'}
    }

    dt = json.dumps(data)
    request_b64 = base64.b64encode(dt.encode()).decode()
    data = {'Request': request_b64,
            'Certificate': generate_certificate(request_b64, st.PRIVATE_KEY_REQUEST, st.PUBLIC_KEY_REQUEST,
                                                st.LICENSE_SIGNATURE_TOOL)
            }
    return data


class ActivationTest(TestCase):
    signature = {'ID': '145', 'Version': 'qqqq'}

    def setUp(self):
        self.ws = Workspace.objects.create(title='testws', config={'isActive': True})
        self.test_device = Device.objects.create(owner=self.ws)
        WorkspaceProperties.objects.create(workspace=self.ws,
                                           template_version=f'template{DEFAULT_TEMPLATES_VERSION}',
                                           auto_create_profiles=False)

    def test_manually(self):
        data = {'Timestamp': '',
                'Signature': {'ID': '141', 'Version': 's'},
                'License': {'Token': self.test_device.token,
                            'Action': 'manually'}}

        with self.subTest():
            data_to_request = data_encode(data)
            response = self.client.post('/rest-api/v1/activate/', data_to_request, content_type='application/json')

            self.assertEqual(response.status_code, 200, msg=base64.standard_b64decode(response.json().get('License')))
            self.assertEqual(Activation.objects.count(), 1)

            response_data = json.loads(response.content)

            activation = Activation.objects.all()[0]
            license_str = base64.b64decode(response_data['License'].encode()).decode()
            activation_token = json.loads(license_str)['License']['Token']

            self.assertEqual(activation_token, activation.token)

            expected = {'License': DummyValue(),
                        'Certificate': DummyValue()}

            self.assertEqual(response_data, expected)

    def test_auto_activate(self):
        activation = Activation.objects.create(signature=self.signature, device=self.test_device)
        data = {
            'Signature': self.signature,
            'License': {
                'Token': activation.token,
                'Action': 'auto',
            },
            'CustomData': {
                'AvailableTemplates': [f'template{DEFAULT_TEMPLATES_VERSION}']
            }
        }

        data = data_encode(data)

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        self.assertEqual(response.status_code, 200, msg=base64.standard_b64decode(response.json().get('License')))
        self.assertEqual(Activation.objects.count(), 2)

        response_data = json.loads(response.content)

        activation = Activation.objects.all().order_by('creation_date')[1]
        license_str = base64.b64decode(response_data['License'].encode()).decode()
        activation_token = json.loads(license_str)['License']['Token']

        self.assertEqual(activation_token, activation.token)

    def test_invalid_data(self):
        activation = Activation.objects.create(signature=self.signature, device=self.test_device)

        expected_error_token = base64.b64encode(json.dumps(
            {
                'Error': 'Invalid token'
            }
        ).encode()).decode()

        expected_error_signature = base64.b64encode(json.dumps(
            {
                'Error': 'Invalid signature'
            }
        ).encode()).decode()

        arr = [
            {
                'Err': {'License': expected_error_token},
                'Signature': self.signature,
                'License': {
                    'Token': '00000000-0000-0000-0000-000000000000',
                    'Action': 'auto'
                }
            },
            {
                'Err': {'License': expected_error_signature},
                'Signature': {'ID': '143', 'Version': ''},
                'License': {
                    'Token': activation.token,
                    'Action': 'auto'
                }
            }
        ]
        for test in arr:
            with self.subTest(msg=f'{test}'):
                data = {'Timestamp': '',
                        'Signature': test['Signature'],
                        'License': test['License']}

                data = data_encode(data)

                response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Activation.objects.count(), 1)

                response_data = json.loads(response.content)
                self.assertEqual(response_data['License'], test['Err']['License'])
                validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                                     st.LICENSE_SIGNATURE_TOOL)

    def test_auto_after_manually(self):
        first_manually = Activation.objects.create(
            signature=self.signature,
            device=self.test_device,
            creation_date=datetime(year=2017, month=1, day=1))

        second_manually = Activation.objects.create(
            signature=self.signature,
            device=self.test_device,
            creation_date=datetime(year=2019, month=1, day=1))

        auto_manually = Activation.objects.create(
            previous_activation=first_manually,
            signature=self.signature,
            device=self.test_device,
            creation_date=datetime(year=2018, month=1, day=1))

        data = {'Timestamp': '',
                'Signature': self.signature,
                'License': {
                    'Token': auto_manually.token,
                    'Action': 'auto'}}

        data = data_encode(data)

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Activation.objects.count(), 3)

    def test_invalid_certificate(self):
        activate = Activation.objects.create(signature=self.signature, device=self.test_device)
        data = {'Signature': self.signature,
                'License': {'Token': activate.token,
                            'Action': 'auto'}}

        data = data_encode(data)
        data['Certificate'] = 'ABCDEFGHABCDEFGHABCDEFGHABCDEFGHABCDEFGHABCDEFGHABCDEFGHABCDEFGH'

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        self.assertEqual(response.status_code, 400)

        response_data = json.loads(response.content)
        expected_error = base64.b64encode(json.dumps(
            {
                'Error': 'Invalid Certificate'
            }
        ).encode()).decode()
        self.assertEqual(response_data['License'], expected_error)
        validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                             st.LICENSE_SIGNATURE_TOOL)

    def test_invalid_json_request(self):
        activate = Activation.objects.create(signature=self.signature, device=self.test_device)
        data = {'Signature': self.signature,
                'License': {'Token': activate.token,
                            'Action': 'ZXC'}  # Error 'Action'. Need 'manually' or 'auto'
                }

        data = data_encode(data)

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        self.assertEqual(response.status_code, 400)

        response_data = json.loads(response.content)

        expected_error = base64.b64encode(json.dumps(
            {
                'Error': 'Invalid JSON request'
            }
        ).encode()).decode()

        self.assertEqual(response_data['License'], expected_error)
        validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                             st.LICENSE_SIGNATURE_TOOL)

    def test_certificate_generation(self):
        certificate = 'cert'

        with self.subTest(msg='Generate certificate'):
            cert = generate_certificate(certificate, st.PRIVATE_KEY_REQUEST, st.PUBLIC_KEY_REQUEST,
                                        st.LICENSE_SIGNATURE_TOOL)

        with self.subTest(msg='Check certificate'):
            validate_certificate(cert, certificate, st.PUBLIC_KEY_REQUEST, st.LICENSE_SIGNATURE_TOOL)

    def test_auto_activate_deleted_device(self):
        test_device = Device.objects.create(owner=self.ws)
        activate = Activation.objects.create(signature=self.signature, device=test_device)
        test_device.delete()

        data = {
            'Signature': self.signature,
            'License': {
                'Token': activate.token,
                'Action': 'auto'
            }
        }

        data = data_encode(data)

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 400)

        expected_error = base64.b64encode(json.dumps(
            {
                'Error': 'Device is blocked'
            }
        ).encode()).decode()

        self.assertEqual(response_data['License'], expected_error)
        validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                             st.LICENSE_SIGNATURE_TOOL)

    def test_auto_activate_with_inactive_workspace(self):
        test_device = Device.objects.create(owner=self.ws)
        activate = Activation.objects.create(signature=self.signature, device=test_device)
        self.ws.config['isActive'] = False
        self.ws.save()

        data = {
            'Signature': self.signature,
            'License': {
                'Token': activate.token,
                'Action': 'auto'
            }
        }

        data = data_encode(data)

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 400)
        expected_error = base64.b64encode(json.dumps(
            {
                'Error': 'Workspace is deactivated'
            }
        ).encode()).decode()

        self.assertEqual(response_data['License'], expected_error)
        validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                             st.LICENSE_SIGNATURE_TOOL)

    def test_invalid_renewal_token(self):
        test_device = Device.objects.create(owner=self.ws)
        activate = Activation.objects.create(signature=self.signature, device=test_device)

        Activation.objects.create(signature=self.signature, device=test_device)

        data = {
            'Signature': self.signature,
            'License': {
                'Token': activate.token,
                'Action': 'auto'
            }
        }

        data = data_encode(data)

        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 400)
        expected_error = base64.b64encode(json.dumps(
            {
                'Error': 'Attempt to reactivation with expired token'
            }
        ).encode()).decode()

        self.assertEqual(response_data['License'], expected_error)
        validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                             st.LICENSE_SIGNATURE_TOOL)

    def test_invalid_activation_token(self):
        data = {'Timestamp': '',
                'Signature': {'ID': '142', 'Version': 's'},
                'License': {
                    'Token': '',
                    'Action': 'manually'}}
        data = data_encode(data)
        response = self.client.post('/rest-api/v1/activate/', data, content_type='application/json')
        response_data = json.loads(response.content)
        self.assertEqual(response.status_code, 400)
        expected_error = base64.b64encode(json.dumps(
            {
                'Error': 'Invalid token'
            }
        ).encode()).decode()

        self.assertEqual(response_data['License'], expected_error)
        validate_certificate(response_data['Certificate'], response_data['License'], st.PUBLIC_KEY_RESPONSE,
                             st.LICENSE_SIGNATURE_TOOL)
