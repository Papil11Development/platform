from enum import Enum
from typing import List, Optional

import strawberry
import strawberry.django as strawberry_django
from django.db.models import QuerySet
from strawberry import ID
from strawberry.types import Info

from licensing.models import Product, License
from platform_lib.types import MutationResult
from platform_lib.utils import get_user
from user_domain.api.v2.types import WorkspaceType


@strawberry.type(description='Data required to complete payment session')
class PaymentOutput(MutationResult):
    redirect_url: str = strawberry.field(description='Redirect URL to complete payment')


@strawberry.enum(description='Payment service names')
class PaymentSource(Enum):
    stripe = 'stripe'


@strawberry.enum(description='Product names')
class ImageAPIServiceNames(Enum):
    face_detector = 'face_detector'


@strawberry.enum(description='Plan modes')
class PlanMode(Enum):
    subscription = 'subscription'


@strawberry.input(description='Data required to create payment session')
class PaymentInput:
    payment_source: PaymentSource = strawberry.field(description='Payment service')
    success_url: str = strawberry.field(description='The URL to which redirect customer when payment is complete')
    cancel_url: str = strawberry.field(description='The URL the customer will be directed to'
                                                   ' if they decide to cancel payment')


@strawberry.type(description='License paid component of plan')
class LicenseMeterAttributeOutput:
    uses: int = strawberry.field(description='Number of used components')
    gross_uses: int = strawberry.field(description='Total components uses')
    allowed: int = strawberry.field(description='Number components that could be used')
    limit: int = strawberry.field(description='Limit of components')

    # TODO: rename to title
    @strawberry.field(description='Name of component')
    def name(self) -> str:
        return self.title  # type: ignore


@strawberry.type(description='Pricing tier')
class PlanTiers:
    flat_amount_decimal: Optional[str] = strawberry.field(description='Price for the entire tier', default=None)
    unit_amount_decimal: Optional[str] = strawberry.field(description='Per unit price for units relevant to the tier',
                                                          default=None)
    up_to: Optional[int] = strawberry.field(description='Gross uses of units available in the tier', default=None)


@strawberry.enum(description='How to compute the price per period')
class PlanBillingScheme(Enum):
    per_unit = 'per_unit'
    tiered = 'tiered'


@strawberry.type(description='Paid component of plan')
class PlanMeterAttribute:
    name: str = strawberry.field(description='Name of component')
    billing_scheme: PlanBillingScheme = strawberry.field(description='How to compute the price per period')
    unit_amount_decimal: Optional[str] = strawberry.field(description='The unit amount in cents.'
                                                                      ' Only set if billing_scheme=per_unit',
                                                          default=None)
    tiers: Optional[List[PlanTiers]] = strawberry.field(description='Pricing tiers.'
                                                                    ' Only set if billing_scheme=tiered',
                                                        default=None)


@strawberry_django.type(Product, description='Paid component of product')
class PlanOutput:
    id: ID = strawberry_django.field(description='Plan id')
    name: 'LicensePlans' = strawberry_django.field(description='Plan name')
    mode: PlanMode = strawberry_django.field(description='Plan mode')
    period: str = strawberry_django.field(description='Period of plan')
    trial_period: Optional[str] = strawberry_django.field(description='Trial period of plan')

    def get_queryset(self, queryset, info):  # return plans that contain in LicensePlans
        return queryset.filter(name__in=[plan.value for plan in LicensePlans])

    @strawberry_django.field(description='Paid components of plan')
    def meter_attributes(self, info: Info) -> List[PlanMeterAttribute]:
        from licensing.payment.managers import PaymentManager
        user = get_user(info)

        result = []
        for attribute in self.get_meter_attributes(qa=user.billing_account.is_qa):  # type: ignore
            price = PaymentManager.get_price(
                payment_source=PaymentSource.stripe,
                price_id=attribute.plan,
                user=user.billing_account
            )
            price_formatted = PlanMeterAttribute(name=attribute.title, billing_scheme=price['billing_scheme'])

            if price['billing_scheme'] == 'tiered':
                price_formatted.tiers = price['tiers']
            elif price['billing_scheme'] == 'per_unit':
                price_formatted.unit_amount_decimal = price['unit_amount_decimal']

            result.append(price_formatted)

        return result


@strawberry.enum(description='Possible license plans')
class LicensePlans(Enum):
    PLATFORM_CLOUD_BASIC = 'platform-cloud-basic'
    # TODO: uncomment after release 1.7
    # PLATFORM_CLOUD_PRO = 'platform-cloud-pro'
    IMAGE_API_BASE = 'image-api-base'
    # IMAGE_API_STARTUP = 'image-api-startup'
    # IMAGE_API_EXPERT = 'image-api-expert'
    # IMAGE_API_ADVANCED = 'image-api-advanced'


@strawberry.enum(description='Possible license states')
class LicenseStatus(Enum):
    active = 'active'
    canceled = 'canceled'
    unpaid = 'unpaid'
    past_due = 'past_due'
    trialing = 'trialing'


@strawberry_django.filter(License)
class LicenseFilter:
    workspace_id: str


@strawberry_django.type(License, filters=LicenseFilter, description="License object")
class LicenseOutput:
    id: ID = strawberry_django.field(description="License id")
    status: LicenseStatus = strawberry_django.field(description="License status")
    cancel_at_period_end: bool = strawberry_django.field(description="Cancel subscription at"
                                                                     " the end of billing period or not")
    meter_attributes: List[LicenseMeterAttributeOutput] = strawberry_django.field(description="Meter attributes "
                                                                                              "for license")
    next_payment_attempt: Optional[str] = strawberry_django.field(description="Date of the next payment attempt")
    workspace: Optional[WorkspaceType] = strawberry_django.field(description="Related workspace")
    plan: PlanOutput = strawberry_django.field(field_name='product', description="Current license plan")
    next_invoice_date: str = strawberry_django.field(field_name='expiration_date',
                                                     description="Date of the next invoice")

    # TODO: remove after frontend integrate workspace field
    @strawberry_django.field(description="Related workspace")
    def workspace_id(self) -> Optional[ID]:
        return self.workspace.id if self.workspace else None

    def get_queryset(self, queryset: QuerySet[License], info: Info):  # return owned user's licenses
        user = get_user(info)
        return queryset.filter(billing_account__user=user)


@strawberry.type(description='Billing information')
class BillingInfoOutput:
    email: str = strawberry.field(description="Billing email")
    is_card_attached: bool = strawberry.field(description="Did user attach card?")


@strawberry.type(description='Result of checking license signature')
class CheckLicenseResult(MutationResult):
    check_signature_key: str
