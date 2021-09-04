from typing import Optional

from django.conf import settings

from licensing.managers import AutonomousLicenseManager, WorkspaceLicenseManager
from licensing.models import BillingAccount
from licensing.payment.stripe.api import StripeAPI


class LicensingOperation:
    @staticmethod
    def create_billing_account(username: str, customer_id: Optional[str] = None) -> bool:
        if not settings.IS_ON_PREMISE:
            billing_account, created = BillingAccount.get_or_create(username=username, customer_id=customer_id)

            if not created:
                return False

            stripe_api = StripeAPI(billing_account)
            stripe_api.get_or_create_customer()
            return True

    @staticmethod
    def create_image_api_license(username: str):
        if not settings.IS_ON_PREMISE:
            return AutonomousLicenseManager.create(
                is_trial=False,
                product_name=AutonomousLicenseManager.ProductName.IMAGE_API_BASE,
                username=username
            )

    @staticmethod
    def create_workspace_license(workspace_id, username: str):
        if not settings.IS_ON_PREMISE:
            return WorkspaceLicenseManager.create(username, workspace_id)
