import base64

from errors import B64Exception


def sample_b64_resolver(sample, bsm_char="$"):
    if type(sample) == list:
        for obj in sample:
            sample_b64_resolver(obj, bsm_char)
    elif type(sample) == dict:
        for k, v in list(sample.items()):
            if k.startswith(bsm_char):
                try:
                    if 'blob' in sample[k]:
                        sample[k]['blob'] = base64.b64decode(v['blob'])
                    else:
                        sample[k] = base64.b64decode(v)
                    sample[k[1:]] = sample[k]
                except base64.binascii.Error:
                    raise B64Exception('Failed to decode base64 string')
                del sample[k]
            if type(v) in [list, dict]:
                sample_b64_resolver(v, bsm_char)


def sample_binary_resolver(sample):
    if type(sample) == list:
        for obj in sample:
            sample_binary_resolver(obj)
    elif type(sample) == dict:
        for k, v in list(sample.items()):
            if type(v) in [list, dict]:
                sample_binary_resolver(v)
            elif type(v) == bytes:
                try:
                    sample["$" + str(k)] = base64.b64encode(sample[k]).decode('ascii')
                    del sample[k]
                except base64.binascii.Error:
                    raise B64Exception('Sample base64 ecoding exception')


def sample_binary_resolver_v2(sample):
    if type(sample) == list:
        for obj in sample:
            sample_binary_resolver_v2(obj)
    elif type(sample) == dict:
        for k, v in list(sample.items()):
            if type(v) == list:
                sample_binary_resolver_v2(v)
            elif type(v) == dict:
                if 'blob' in v.keys():
                    sample['_' + str(k)] = v
                    del sample[k]
                sample_binary_resolver_v2(v)
            elif type(v) == bytes:
                try:
                    sample[k] = base64.b64encode(sample[k]).decode('ascii')
                except base64.binascii.Error:
                    raise B64Exception('Sample base64 ecoding exception')
