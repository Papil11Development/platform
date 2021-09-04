from typing import Optional, Tuple

from django.conf import settings

from licensing.managers import WorkspaceLicenseManager, MeterAttributeManager, AutonomousLicenseManager, \
    BaseLicenseManager
from licensing.policies import image_api_service_mapping
from licensing.utils import TransactionValidator
from platform_lib.exceptions import LicenseException, LicenseLimitAttribute

if settings.IS_ON_PREMISE:  # TODO improve this somehow
    from licensing.cryptlex_api import LicenseControllerOnPremise
    lic_manager_on_prem = LicenseControllerOnPremise(settings.LIC_PRODUCT_ID, settings.LIC_SERVER_URL)


class LicensingCommonEvent:
    CAMERA_METER_ATTR = MeterAttributeManager.Title.CHANNELS.value
    PERSON_METER_ATTR = MeterAttributeManager.Title.PERSONS_IN_BASE.value

    def __init__(self, workspace_id: Optional[str] = None):
        self.workspace_id = workspace_id

    def create_cameras(self, cameras_n_total: Optional[int] = None, operation_diff_n: int = 1):
        if settings.IS_ON_PREMISE:
            lic_manager_on_prem.validate_meter_attr_allowed_uses(self.CAMERA_METER_ATTR, cameras_n_total)
        else:
            if self.workspace_id:
                WorkspaceLicenseManager.increment_meter_attribute(self.workspace_id,
                                                                  self.CAMERA_METER_ATTR,
                                                                  operation_diff_n)
            else:
                raise LicenseException('Internal error: create cameras with no workspace id')

    def delete_cameras(self, cameras_n_total: Optional[int] = None, operation_diff_n: int = 1):
        if settings.IS_ON_PREMISE:
            pass
        else:
            if self.workspace_id:
                WorkspaceLicenseManager.decrement_meter_attribute(self.workspace_id,
                                                                  self.CAMERA_METER_ATTR,
                                                                  operation_diff_n)
            else:
                raise LicenseException('Internal error: delete cameras with no workspace id')

    def create_persons(self, persons_n_total: Optional[int] = None, operation_diff_n: int = 1):
        if settings.IS_ON_PREMISE:
            lic_manager_on_prem.validate_meter_attr_allowed_uses(self.PERSON_METER_ATTR, persons_n_total)
        else:
            if self.workspace_id:
                WorkspaceLicenseManager.increment_meter_attribute(self.workspace_id,
                                                                  self.PERSON_METER_ATTR,
                                                                  operation_diff_n)
            else:
                raise LicenseException('Internal error: create persons with no workspace id')

    def delete_persons(self, persons_n_total: Optional[int] = None, operation_diff_n: int = 1):
        if settings.IS_ON_PREMISE:
            pass
        else:
            if self.workspace_id:
                WorkspaceLicenseManager.decrement_meter_attribute(self.workspace_id,
                                                                  self.PERSON_METER_ATTR,
                                                                  operation_diff_n)
            else:
                raise LicenseException('Internal error: delete persons with no workspace id')

    @staticmethod
    def check_capturer_uses(ia_service_name: str, access: str, signature: Optional[str]) -> Tuple[bool, str]:
        ok = False
        if settings.IS_ON_PREMISE:
            meter_attr_name = f"{ia_service_name}_transactions"
            try:
                lic_manager_on_prem.validate_increment_floating_meter_attr(meter_attr_name)
                ok = True
            except LicenseLimitAttribute:
                ok = False
        else:
            product_names, attribute_name = image_api_service_mapping[ia_service_name]

            capturer_license = AutonomousLicenseManager.get_all_active_licenses().filter(
                product__name__in=product_names, billing_account__user__accesses=access
            ).first()

            if capturer_license is not None:
                ok = BaseLicenseManager.check_meter_attribute(capturer_license, attribute_name)

        return ok, TransactionValidator(signature).encrypt()

    @staticmethod
    def add_capturer_usage(ia_service_name: str, access: str) -> bool:
        if settings.IS_ON_PREMISE:
            lic_manager_on_prem.increment_floating_meter_attr(f"{ia_service_name}_transactions", 1)
            ok = True
        else:
            product_names, attribute_name = image_api_service_mapping[ia_service_name]

            capturer_license = AutonomousLicenseManager.get_all_active_licenses().get(
                product__name__in=product_names,
                billing_account__user__accesses__id=access
            )

            BaseLicenseManager.increment_meter_attribute(capturer_license, attribute_name)

            ok = True

        return ok
