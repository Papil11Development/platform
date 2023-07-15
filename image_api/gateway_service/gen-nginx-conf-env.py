import sys
from copy import deepcopy

import crossplane

payload = crossplane.parse('./base_nginx.conf')

config = payload['config'][0]['parsed']


server_block = config[5]['block'][8]['block']

base_location = deepcopy(server_block[3])
del server_block[3]


def env_template_proc(service_name):
    proc_service_url = f'{service_name}_URL'
    return proc_service_url, "export PROC_SERVICE_URL=http://${PROC_SERVICE_HOST}:${PROCESSING_PORT}"\
        .replace('PROC_SERVICE', service_name)


with open('./env.sh', 'w') as f:
    urls = []
    for service in sys.argv[1].split(','):

        base_service = deepcopy(base_location)

        base_service['args'][0] = base_service['args'][0].replace('processing-service', service)
        env_service_name = service.upper().replace('-', '_')
        base_service['block'][1]['args'][0] = base_service['block'][1]['args'][0]\
            .replace('PROCESSING_SERVICE', env_service_name)
        server_block.append(base_service)
        proc_service_url, url_composition_template = env_template_proc(env_service_name)
        urls.append(proc_service_url)
        f.write(url_composition_template + "\n")

    url_composition_template = urls + ["INDEX_FILENAME", "LIMIT_CONN_SIZE"]
    env_subs = ",".join(map(lambda x: f'$'+"{"+x+"}", url_composition_template))
    f.write(f"export ENV_SUBSSTR='{env_subs}'" + "\n")

with open('nginx.conf', 'w') as f:
    f.write(crossplane.build(config))
