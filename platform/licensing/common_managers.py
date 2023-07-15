from typing import Optional, Tuple

from django.conf import settings
from plib.licensing.api import License as LicenseAPI  # type: ignore
from plib.licensing.exceptions import LicenseLimitAttribute as NewLicenseLimitAttribute  # type: ignore

from licensing.managers import (AutonomousLicenseManager, BaseLicenseManager,
                                MeterAttributeManager, WorkspaceLicenseManager)
from licensing.policies import image_api_service_mapping
from licensing.utils import TransactionValidator
from platform_lib.exceptions import LicenseException, LicenseLimitAttribute


class LicensingCommonEvent:
    CAMERA_METER_ATTR = MeterAttributeManager.Title.CHANNELS.value
    PERSON_METER_ATTR = MeterAttributeManager.Title.PERSONS_IN_BASE.value

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.license_api = LicenseAPI(
            url=f'{settings.LICENSE_SERVICE_URL}/graphql/v1',
            issuer=settings.JWT_SVC_NAME,
            jwt_key=settings.JWT_ENCODE_SECRET,
            jwt_algorithm=settings.JWT_ALGORITHM,
            salt=settings.ENCRYPTOR_SALT,
            workspace_id=workspace_id,
        )

    def create_cameras(self, cameras_n_total: Optional[int] = None, operation_diff_n: int = 1):
        if settings.IS_ON_PREMISE:
            try:
                self.license_api.update_resource(self.CAMERA_METER_ATTR, cameras_n_total)
            except NewLicenseLimitAttribute as ex:
                raise LicenseLimitAttribute(ex.attribute)
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
            try:
                self.license_api.update_resource(self.PERSON_METER_ATTR, persons_n_total)
            except NewLicenseLimitAttribute as ex:
                raise LicenseLimitAttribute(ex.attribute)
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
            # TODO: ImageAPI licensing
            raise NotImplementedError
            # meter_attr_name = f"{ia_service_name}_transactions"
            # try:
            #     lic_manager_on_prem.validate_increment_floating_meter_attr(meter_attr_name)  # type: ignore
            #     ok = True
            # except LicenseLimitAttribute:
            #     ok = False
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
            # TODO: ImageAPI licensing
            raise NotImplementedError
            # lic_manager_on_prem.increment_floating_meter_attr(f"{ia_service_name}_transactions", 1)  # type: ignore
            # ok = True
        else:
            product_names, attribute_name = image_api_service_mapping[ia_service_name]

            capturer_license = AutonomousLicenseManager.get_all_active_licenses().get(
                product__name__in=product_names,
                billing_account__user__accesses__id=access
            )

            BaseLicenseManager.increment_meter_attribute(capturer_license, attribute_name)

            ok = True

        return ok

    def is_active(self) -> bool:
        if settings.IS_ON_PREMISE:
            license_ = self.license_api.license()
            return license_.status.lower() == 'active'
        else:
            raise NotImplementedError
