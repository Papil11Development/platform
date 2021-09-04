import datetime
import logging
from abc import abstractmethod, ABC
from time import sleep

from cryptlex.lexfloatclient import LexFloatClient, LexFloatStatusCodes, LexFloatClientException
from cryptlex.lexfloatclient.lexfloatclient import LicenseMeterAttribute

from platform_lib.exceptions import LicenseLimitAttribute
from user_domain.managers import WorkspaceManager
from user_domain.models import Workspace


logger = logging.getLogger(__name__)


def cryptlex_operation_exc_handler(func):
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except LexFloatClientException as ex:
            if ex.code == LexFloatStatusCodes.LF_E_NO_LICENSE:
                self.request_license()
            elif ex.code == LexFloatStatusCodes.LF_E_METER_ATTRIBUTE_USES_LIMIT_REACHED:
                raise LicenseLimitAttribute(args[0])
            else:
                raise ex
            return func(self, *args, **kwargs)
    return wrapper


def cryptlex_unlimited_meter_attribute(func):
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except LexFloatClientException as ex:
            if ex.code == LexFloatStatusCodes.LF_E_METER_ATTRIBUTE_NOT_FOUND:
                return
            else:
                raise ex
    return wrapper


class CryptlexFloatLicenseManager(ABC):
    CONN_TRIES = 5

    def __init__(self, product_id: str, lic_server_url: str):
        LexFloatClient.SetHostProductId(product_id)
        LexFloatClient.SetHostUrl(lic_server_url)
        LexFloatClient.SetFloatingLicenseCallback(self.lic_callback)
        self.request_license()

    def __del__(self):
        LexFloatClient.DropFloatingLicense()

    @abstractmethod
    def lic_callback(self, status):
        raise NotImplementedError

    def request_license(self):
        while True:
            try:
                LexFloatClient.RequestFloatingLicense()
            except Exception as ex:
                sleep(5)
                print(ex)
            break

    @cryptlex_operation_exc_handler
    @cryptlex_unlimited_meter_attribute
    def increment_floating_meter_attr(self, key: str, value: int):
        LexFloatClient.IncrementFloatingClientMeterAttributeUses(key, value)

    @cryptlex_operation_exc_handler
    def decrement_floating_meter_attr(self, key: str, value: int):
        LexFloatClient.DecrementFloatingClientMeterAttributeUses(key, value)

    @cryptlex_operation_exc_handler
    def set_floating_metadata(self, key: str, value: str):
        LexFloatClient.SetFloatingClientMetadata(key, value)

    @cryptlex_operation_exc_handler
    def get_floating_meter_uses(self, key: str):
        return LexFloatClient.GetFloatingClientMeterAttributeUses(key)

    @cryptlex_operation_exc_handler
    def get_host_lic_metadata(self, key: str):
        return LexFloatClient.GetHostLicenseMetadata(key)

    @cryptlex_operation_exc_handler
    def get_host_expiry_date(self) -> datetime.datetime:
        return datetime.datetime.utcfromtimestamp(LexFloatClient.GetHostLicenseExpiryDate())

    @cryptlex_operation_exc_handler
    def get_host_meter_attr(self, key: str) -> LicenseMeterAttribute:
        return LexFloatClient.GetHostLicenseMeterAttribute(key)

    @cryptlex_operation_exc_handler
    @cryptlex_unlimited_meter_attribute
    def validate_meter_attr_allowed_uses(self, key: str, uses: int):
        if LexFloatClient.GetHostLicenseMeterAttribute(key).allowed_uses < uses:
            raise LicenseLimitAttribute(key)

    @cryptlex_operation_exc_handler
    @cryptlex_unlimited_meter_attribute
    def validate_increment_floating_meter_attr(self, key: str, value: int = 1):
        attr = self.get_host_meter_attr(key)
        if attr.total_uses + value > attr.allowed_uses:
            raise LicenseLimitAttribute(key)


class LicenseControllerOnPremise(CryptlexFloatLicenseManager):
    def __init__(self, product_id: str, lic_server_url: str):
        super(LicenseControllerOnPremise, self).__init__(product_id, lic_server_url)

    def lic_callback(self, status_code):
        logger.info(f'LexFloatServer status: {status_code}')
        resolving_operation = (WorkspaceManager.activate_workspace if status_code == 0
                               else WorkspaceManager.deactivate_workspace)
        for ws in Workspace.objects.filter(config__is_active=bool(status_code)):
            resolving_operation(ws)
