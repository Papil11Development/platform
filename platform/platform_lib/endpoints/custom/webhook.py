from abc import ABC

from notifiers.core import Provider, Response
from notifiers.utils.requests import RequestsHelper


class Webhook(Provider, ABC):
    """Webhook notifications"""

    name = "webhook"

    base_url = None
    site_url = None

    _required = {'required': ['url', 'method']}

    _schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "title": "Request url"
            },
            "method": {
                "type": "string",
                "title": "Request method",
                "enum": ["get", "post", "put", "delete", "patch"]
            },
            "params": {
                'type': 'array',
                "title": "Request params",
                'items': {'type': 'string'}
            },
            "headers": {
                'type': 'array',
                "title": "Request headers",
                'items': {'type': 'string'}
            },
            "request_data": {
                "title": "Request data",
                'type': 'object'
            },
            "cookies": {
                "title": "Request cookies",
                'type': 'object'
            },
            "files": {
                "title": "Path to request files",
                'type': 'array',
                'items': {'type': 'string'}
            },
        },
        'required': ['url', 'method'],
        "additionalProperties": False,
    }

    def _send_notification(self, data: dict) -> Response:
        url = data.get("url")
        method = data.get("method")
        params = data.get("params")
        headers = data.get("headers")
        request_data = data.get("request_data")
        cookies = data.get("cookies")
        files = data.get("files")

        response, errors = RequestsHelper.request(method=method,
                                                  url=url,
                                                  params=params,
                                                  headers=headers,
                                                  json=request_data,
                                                  cookies=cookies,
                                                  files=files)

        return self.create_response(data, response, errors)
