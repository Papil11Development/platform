import json
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist


class CodedException(Exception):
    exception_messages = {
        "limits": {
            "0x1a504098": "Transaction per second limit exceeded",
            "0xf131f89a": "Profiles per workspace limit exceeded",
            "0xf5409e8c": "Samples per person limit exceeded",
            "0x1fdc14b6": "{}",
            "0x6245cd00": "{}",
        },
        "bad_input_data": {
            "0x87b68438": "One of the parameters sampleData or sampleId is required",
            "0x963fb254": "One of the parameters sourceSampleData or sourceSampleId or sourceImage is required",
            "0xnf5825dh": "One of the parameters sampleData or sourceImage is required",
            "0xae6369b2": "One of the parameters groupId or groupIds is required",
            "0xe509f74d": "One of the parameters agentId or agentIds is required",
            "0x34586954": "At least image or template is required",
            "0x30d36040": "Sample already used",
            "0x51b4c0e2": "Could\'t delete one or several profiles",
            "0xbd98c4fc": "List of a profiles ids must not be empty",
            "0xc3358b52": "Could not identify (or identify more than 1) face from this sample (face count = {})",
            "0xc69c44d4": "Sample Data is not valid",
            "0xc9e01940": "Session already closed",
            "0xcd16d41e": "Requires session id",
            "0xd2ae0c62": "Empty agents ids list",
            "0xd2ae0ef8": "Empty profiles ids list",
            "0xd658ea62": "Empty query",
            "0xe23f8aac": "Sample does not exist",
            "0xe5767afa": "Tasks {} not found",
            "0xf023e8b6": "The profile with this sample does not exist",
            "0xf47f116a": "Confidence threshold must be between 0 and 1",
            "0xf8be6762": "Max num of candidates must be between 1 and 100",
            "0x006dd808": "Image width is over the limit",
            "0x006dd809": "Image height is over the limit",
            "0x03b73f98": "File size larger than {}",
            "0x15449f83": "{} event already exists in this session",
            "0xcac45dce": "Lost event must be created after Found event in this session",
            "0xf7212879": "creationDate of Lost event must be later than creationDate of Found event in this session",
            "0x81dcd1d4": "Different profiles required",
            "0x581bd57e": "There are no samples for merge",
            "0x95bg42fd": "No faces found",
            "0x35vd45ms": "More than 1 face has been identified on this image",
            "0x86bd49dh": "Low quality photo",
            "0x573bkd35": "One or several profiles_groups does not exist",
            "0x86bjl434": "One or several activities does not exist",
            "0x943b3c24": "One or several samples does not exist",
            "0x358vri3s": "Activity is anonymous"
        },
        "balance": {
            "0x50028bd4": "Low balance",
        },
        "internal": {
            "0x20bdf91c": "Can't download file. Error: {}",
            "0x3091b6e4": "Can't process file. Error: {}",
            "0x312cf586": "Can't add agent. Error: {}",
            "0x176cbb31": "Unable to perform verification. Error: {}"
        },
        "other": {
            "0x4caabee8": "This session is anonymous",
            "0x500c29fa": "You are not Authorized"
        }
    }

    def __init__(self, code, ex_type=None, message=None):
        template = self.find_message(code, ex_type)
        message = template.format(message)
        # TODO remove after front fix
        message = json.dumps({"message": message, "code": code})
        super().__init__(message)
        self.code = code
        self.message = message

    def find_message(self, code, ex_type=None):
        if ex_type:
            t = self.exception_messages.get(ex_type)
            if not t:
                return "Unknown exception type"
            if code in t.keys():
                return t[code]
            return f"Unknown exception code for \'{ex_type}\' type"
        else:
            for key in self.exception_messages.keys():
                if code in self.exception_messages[key]:
                    return self.exception_messages[key][code]
            return "Unknown exception code"


class LimitException(CodedException):
    def __init__(self, code, message=None):
        super().__init__(code, "limits", message)


class BadInputDataException(CodedException):
    def __init__(self, code, message=None):
        super().__init__(code, "bad_input_data", message)


class BalanceException(CodedException):
    def __init__(self, code, message=None):
        super().__init__(code, "balance", message)


class InternalException(CodedException):
    def __init__(self, code, message=None):
        super().__init__(code, "internal", message)


def format_coded_error(error: CodedException):
    return {
        'message': error.message,
        'code': error.code,
    }


def format_internal_error(error: Exception):
    return {
        'message': str(error),
    }


class TokenExpired(Exception):
    def __str__(self):
        return 'Attempt to reactivation with expired token'


class InvalidSignature(Exception):
    def __str__(self):
        return 'Invalid signature'


class AgentIsBlocked(Exception):
    def __str__(self):
        return 'Agent is blocked'


class WorkspaceInactive(Exception):
    def __str__(self):
        return 'Workspace is deactivated'


class InvalidClientTimestamp(Exception):
    def __str__(self):
        return 'Invalid client timestamp'


class TemplateValidationError(Exception):
    def __str__(self):
        return 'Unsupported template version'


class InvalidJsonRequest(Exception):
    def __str__(self):
        return 'Invalid JSON request'


class InvalidToken(Exception):
    def __str__(self):
        return 'Invalid token'


class EmptyToken(Exception):
    def __str__(self):
        return 'Token is empty'


class KibanaError(Exception):
    message = None

    def __init__(self, message: str, workspace_id: Optional[str] = None):
        self.message = message
        if workspace_id:
            self.message = f'[ws.id:{workspace_id}]. {message}'
        super().__init__(self.message)

    def __str__(self):
        return self.message


class LicenseException(Exception):
    pass


class LicenseExpired(LicenseException):
    def __str__(self):
        return 'License expired'


class LicenseNotExist(LicenseException, ObjectDoesNotExist):
    def __str__(self):
        return 'License does not exist'


class LicenseAttributeNotExist(LicenseException):
    def __init__(self, attribute):
        self.attribute = attribute
        super().__init__()

    def __str__(self):
        return f'License meter-attribute "{self.attribute}" does not exist'


class LicenseAttributeNotMeter(LicenseException):
    def __init__(self, attribute):
        self.attribute = attribute
        super().__init__()

    def __str__(self):
        return f'License attribute "{self.attribute}" is not meter'


class ProductAttributeNotExist(LicenseException):
    def __init__(self, attribute):
        self.attribute = attribute
        super().__init__()

    def __str__(self):
        return f'Product meter-attribute "{self.attribute}" does not exist'


class LicenseLimitAttribute(LicenseException):
    def __init__(self, attribute):
        self.attribute = attribute
        super().__init__()

    def __str__(self):
        return f'License attribute "{self.attribute}" limit exceeded'


class LicenseUpgradeFail(LicenseException):
    def __init__(self, message):
        self.message = message
        super().__init__()

    def __str__(self):
        return f'License upgrade fail: {self.message}'


class InvalidJsonSchema(Exception):
    pass


class InvalidTriggerMetaJson(InvalidJsonSchema):
    def __str__(self):
        return 'Invalid trigger meta json'


class LicenseIsTrial(LicenseException):
    pass


class LicenseNotPaid(LicenseException):
    pass


class StripeException(Exception):
    pass


class PaymentMethodNotExist(StripeException):
    pass


class StripeDuplicateWebhook(StripeException):
    pass


class CognitiveWebhook(StripeException):
    pass


class StripePaymentFailed(StripeException):
    pass


class OnPremNotImplemented(LicenseException):
    pass
