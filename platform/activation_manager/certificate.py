import os
import subprocess
import json
import tempfile

from django.conf import settings

SUBPROCESS_TIMEOUT = 10


class SignatureToolError(Exception):
    def __init__(self, message: str):
        self.__message = message

    def __str__(self):
        return self.__message


def generate_certificate(token: str, private_key, public_key, license_signature_tool):
    with tempfile.NamedTemporaryFile() as license_file:
        cmd = f'{license_signature_tool} ' \
              f'--public-key {public_key} ' \
              f'--private-key {private_key} ' \
              f'-s {token} ' \
              f'-n {license_file.name} '
        __run_process(cmd)

        return json.loads(license_file.read())[settings.ACTIVATION_LICENSE_NAME]


def validate_certificate(certificate, token: str, public_key: str, license_signature_tool: str):
    cmd = f'{license_signature_tool} ' \
          f'-v --public-key {public_key} ' \
          f'-s {token} -c {certificate}'
    __run_process(cmd)


def __run_process(cmd: str):
    try:
        process = subprocess.run(cmd, timeout=SUBPROCESS_TIMEOUT, shell=True, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise SignatureToolError('Signature tool timed out')

    if process.returncode != 0:
        raise SignatureToolError('Invalid Certificate')
