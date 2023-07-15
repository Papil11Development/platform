from api.sdk.errors import InvalidContextException, BlockInitialisationException


class RequestException(Exception):
    def __init__(self, message):
        self._message = message

    def __str__(self):
        return self._message


class B64Exception(RequestException):
    pass
