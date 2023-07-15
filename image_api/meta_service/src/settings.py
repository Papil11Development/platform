import json
import os
import re

with open('config.json', 'r', encoding='utf-8') as config:
    CONFIG = json.load(config)

BLOCK_CONFIG = CONFIG['block_config']


def bool_env_convert_func(env_name):
    e = os.environ.get(env_name)
    return bool(int(e)) if e else False


BLOCK_CONFIG['use_avx2'] = bool_env_convert_func('ENABLE_USE_AVX2')
BLOCK_CONFIG['use_cuda'] = bool_env_convert_func('ENABLE_USE_CUDA')
BLOCK_CONFIG['downscale_rawsamples_to_preferred_size'] = bool_env_convert_func('DOWNSCALE_RAWSAMPLES')

GRPC_QUALITY_BLOCKS = ['_QUALITY_LIVENESS_ANTI_SPOOFING']
GRPC_BLOCKS = ['_LIVENESS_ANTI_SPOOFING']
GRPC_SERVICE_URL = os.environ.get('GRPC_SERVICE_URL')
GRPC_ACCESS_TOKEN = os.environ.get('GRPC_ACCESS_TOKEN')

OBJECTS_KEY = "objects"

PROCESSING_DEPENDENCIES = CONFIG.get('dependencies', [])
meta_config = CONFIG.get('meta_config', {})

VERSION_CONFIG = meta_config['versions']
BLOCK_CONFIG['versions'] = list(VERSION_CONFIG.keys())
CONVERSION_NEEDLE = meta_config['conversion_needle']


RECOGNIZER_CONFIG = os.environ.get('RECOGNIZER_CONFIG')
if RECOGNIZER_CONFIG:
    BLOCK_CONFIG['recognizer_config'] = RECOGNIZER_CONFIG
else:
    RECOGNIZER_CONFIG = BLOCK_CONFIG.get('recognizer_config')

if RECOGNIZER_CONFIG:
    RECOGNIZER_VERSION = re.search("method(.*)_recognizer.xml", RECOGNIZER_CONFIG).group(1)


CAPTURER_CONFIG = os.environ.get('CAPTURER_CONFIG')
if CAPTURER_CONFIG:
    BLOCK_CONFIG['capturer_config'] = CAPTURER_CONFIG
else:
    CAPTURER_CONFIG = BLOCK_CONFIG.get('capturer_config')


UNIT_TYPE = BLOCK_CONFIG['unit_type']

__face_sdk_path = os.environ.get("FACE_SDK_DIR",  './face_sdk')
FACE_SDK_DLL_PATH = os.path.join(__face_sdk_path, 'lib', 'libfacerec.so')
FACE_SDK_CONF_DIR_PATH = os.path.join(__face_sdk_path, 'conf', 'facerec')

WORKERS = os.environ['WORKERS']
PORT = os.environ['PORT']

# Limits
MAX_BODY_SIZE = int(os.environ['MAX_BODY_SIZE']) * 1000000

# Product Information
APP_VERSION = os.environ['APP_VERSION']
TERMS_URL = os.environ['TERMS_URL']
CONTACT_NAME = os.environ['CONTACT_NAME']
CONTACT_URL = os.environ['CONTACT_URL']
CONTACT_PRODUCT_NAME = os.environ['CONTACT_PRODUCT_NAME']
IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT = bool(os.environ.get('IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT'))

APP_ROOT_PATH = os.environ['ROOT_PATH']

APP_ROOT_PATH = "" if APP_ROOT_PATH == '/' else APP_ROOT_PATH + '/'  # may cause problems

SERVICE_NAME = f"{UNIT_TYPE.lower()}-{APP_VERSION}"
TRACING_ENABLED = json.loads(os.environ.get('TRACING_ENABLED', "False").lower())
TRACER_HOST = os.environ.get('TRACER_HOST', "0.0.0.0")
TRACER_PORT = os.environ.get('TRACER_PORT', 4317)
TRACER_URL = f"http://{TRACER_HOST}:{TRACER_PORT}"
