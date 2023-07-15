class SDKException(Exception):
    def __init__(self, message):
        self._message = message

    def __str__(self):
        return self._message


class InvalidContextException(SDKException):
    pass


class BlockInitialisationException(SDKException):
    pass


class UnknownUnitType(SDKException):
    pass
