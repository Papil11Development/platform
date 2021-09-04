from typing import List, Optional

import strawberry
import strawberry.django as strawberry_django
from django.core.exceptions import ObjectDoesNotExist
from strawberry.arguments import UNSET
from strawberry.types import Info
from strawberry_django.filters import apply

from licensing.api.v2.types import LicenseOutput, PlanOutput, ImageAPIServiceNames, BillingInfoOutput, LicenseFilter, \
    CheckLicenseResult
from licensing.common_managers import LicensingCommonEvent
from licensing.models import License
from licensing.payment.stripe.api import StripeAPI
from platform_lib.exceptions import StripeException
from platform_lib.strawberry_auth.permissions import IsAuthenticated, IsAccessToken
from platform_lib.utils import get_user, get_token


# TODO: remove after frontend will use filters instead bare workspace_id
def resolver_licenses(info: Info,
                      filters: Optional[LicenseFilter] = UNSET,
                      workspace_id: Optional[str] = None) -> List[LicenseOutput]:
    queryset = License.objects.all()
    if workspace_id:
        filters = LicenseFilter(workspace_id=workspace_id)  # type: ignore
    queryset = apply(filters, queryset)
    return LicenseOutput.get_queryset(None, queryset, info)  # type: ignore


@strawberry.type
class InternalQuery:
    plans: List[PlanOutput] = strawberry_django.field(permission_classes=[IsAuthenticated],
                                                      description='List of Plans')
    licenses: List[LicenseOutput] = strawberry_django.field(permission_classes=[IsAuthenticated],
                                                            description='List of licenses',
                                                            resolver=resolver_licenses)

    @strawberry.field(permission_classes=[IsAccessToken], description='Check the acceptability of the operation'
                                                                      ' on the attribute')
    def check_capturer_attribute(self,
                                 info: Info,
                                 ia_service_name: ImageAPIServiceNames,
                                 signature: Optional[str] = None, ) -> CheckLicenseResult:
        access_token = get_token(info=info)

        check_result, encrypted_signature = LicensingCommonEvent.check_capturer_uses(
            ia_service_name.value,
            access_token,
            signature
        )

        return CheckLicenseResult(ok=check_result, check_signature_key=encrypted_signature)

    @strawberry.field(permission_classes=[IsAuthenticated], description="User's billing information")
    def billing_info(self, info: Info) -> BillingInfoOutput:
        user = get_user(info)
        try:
            customer = StripeAPI.get_customer(user.billing_account.stripe_customer_id)
        except StripeException:
            raise Exception('Stripe customer does not exist')
        except ObjectDoesNotExist:
            raise Exception('Internal server error: billing account does not exist')

        if customer.get('deleted', False):
            raise Exception("Stripe customer was deleted")

        return BillingInfoOutput(
            email=customer.email,
            is_card_attached=customer.invoice_settings.default_payment_method is not None
        )
