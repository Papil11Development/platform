from typing import List
from platform_lib.endpoints.custom.webhook import Webhook


class WebhookManager:
    """
    Webhook notification manager
    """
    @classmethod
    def send_message(cls,
                     url: str,
                     method: str,
                     request_data: dict,
                     headers: List[str] = None,
                     params: List[str] = None):
        """
        Send email message to target

        Parameters
        ----------
        url: str
            Webhook web address
        method: str
            Request method
        request_data: dict
            Request json data
        headers: List[str]
            List of request headers
        params: List[str]
            List of request url params
        """

        webhook = Webhook()

        kwargs = {
            "url": url,
            "method": method.lower(),
            "request_data": request_data,
        }

        if headers is not None:
            kwargs["headers"] = headers

        if params is not None:
            kwargs["params"] = params

        webhook.notify(**kwargs, raise_on_errors=True)
