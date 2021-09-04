import strawberry
from strawberry.types import Info

from licensing.api.v2.types import PaymentInput, PaymentOutput, PaymentSource, ImageAPIServiceNames, LicensePlans
from licensing.common_managers import LicensingCommonEvent
from licensing.models import Product
from licensing.payment.managers import PaymentManager
from licensing.payment.stripe.api import StripeAPI
from licensing.utils import verify_license_plan_change
from platform_lib.strawberry_auth.permissions import IsAuthenticated, IsLicenseExists, IsAccessToken
from platform_lib.data.common_models import SubscriptionStatus
from platform_lib.exceptions import LicenseUpgradeFail, LicenseIsTrial, LicenseException, PaymentMethodNotExist, \
    LicenseNotPaid, StripeException, StripePaymentFailed
from platform_lib.types import MutationResult
from platform_lib.utils import get_token, get_user


@strawberry.type
class InternalMutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated, IsLicenseExists], description='Upgrade subscription')
    def upgrade_subscription(self, info: Info) -> MutationResult:
        lic = info.context.request.META['license']

        if not lic.is_trial:
            raise LicenseUpgradeFail('License is already upgraded')

        customer = StripeAPI.get_customer(lic.billing_account.stripe_customer_id)

        if customer['invoice_settings']['default_payment_method']:
            stripe_api = StripeAPI(lic.billing_account)
            stripe_api.stop_trial_for_subscription(lic.subscription_id)
        else:
            raise PaymentMethodNotExist('Payment method does not configured')

        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsAuthenticated, IsLicenseExists], description='Cancel subscription')
    def cancel_subscription(self, info: Info) -> MutationResult:
        lic = info.context.request.META['license']

        PaymentManager.cancel_subscription(PaymentSource.stripe, lic)

        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsAuthenticated, IsLicenseExists], description='Activate subscription')
    def activate_subscription(self, info: Info) -> MutationResult:
        lic = info.context.request.META['license']

        PaymentManager.activate_subscription(PaymentSource.stripe, lic)

        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsAuthenticated, IsLicenseExists],
                         description='Change product plan')
    def change_plan(self, info: Info, plan_name: LicensePlans) -> MutationResult:
        lic = info.context.request.META['license']
        user = get_user(info)

        if lic.is_trial:
            raise LicenseIsTrial('Upgrade your license before using these features')
        elif lic.status not in [SubscriptionStatus.ACTIVE.value]:
            raise LicenseNotPaid('Pay for the license before using these features')
        elif lic.product is None:
            raise LicenseException('Internal error: license has not product')
        elif lic.product.name == plan_name.value:
            raise LicenseException(f'License already have plan "{plan_name.value}"')

        try:
            product = Product.get_product_by_name(plan_name.value)
        except Product.DoesNotExist:
            raise LicenseException(f"Product '{plan_name.value}' does not exist")

        is_valid, operation, replace_items, error_message = verify_license_plan_change(product, lic)

        if is_valid and operation:  # and condition for mypy
            meter_attributes_plans = product.get_product_plans(qa=user.billing_account.is_qa)

            subscription = PaymentManager.change_plan(PaymentSource.stripe,
                                                      lic,
                                                      meter_attributes_plans,
                                                      operation,
                                                      replace_items)
        else:
            raise LicenseException(error_message)

        if subscription is None:
            raise LicenseException('Change of plan fails')

        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsAuthenticated],
                         description='Update payment method')
    def update_payment_method(self, info: Info, payment_input: PaymentInput) -> PaymentOutput:
        user = get_user(info)

        session = PaymentManager.update_payment_method(user.billing_account,
                                                       payment_input.success_url,
                                                       payment_input.cancel_url)

        return PaymentOutput(ok=True, redirect_url=session.url)

    @strawberry.mutation(permission_classes=[IsAuthenticated],
                         description='Detach payment method')
    def detach_payment_method(self, info: Info) -> MutationResult:
        user = get_user(info)

        stripe_api = StripeAPI(user.billing_account)
        customer = StripeAPI.get_customer(user.billing_account.stripe_customer_id)
        exist_payment_method = customer['invoice_settings']['default_payment_method']

        if exist_payment_method:
            stripe_api.detach_payment_method(exist_payment_method)
        else:
            raise LicenseException('Payment method not attached')

        return MutationResult(ok=True)

    @strawberry.mutation(permission_classes=[IsAuthenticated, IsLicenseExists], description='Pay invoice')
    def pay_invoice(self, info: Info, payment_input: PaymentInput) -> PaymentOutput:
        user = get_user(info)
        lic = info.context.request.META['license']
        url = ''
        ok = True

        if lic.is_trial:
            raise LicenseIsTrial('Upgrade your license before use this actions')
        elif lic.status not in [SubscriptionStatus.UNPAID.value, SubscriptionStatus.CANCELED.value]:
            raise StripeException('There are no open invoices')  # TODO: Refine raise message

        customer = StripeAPI.get_customer(user.billing_account.stripe_customer_id)
        if customer.invoice_settings.default_payment_method is None:
            session = PaymentManager.update_payment_method(user.billing_account,
                                                           payment_input.success_url,
                                                           payment_input.cancel_url)
            ok = False
            url = session.url
        else:
            try:
                PaymentManager.try_pay_invoice(PaymentSource.stripe, lic)
            except StripePaymentFailed:
                session = PaymentManager.update_payment_method(user.billing_account,
                                                               payment_input.success_url,
                                                               payment_input.cancel_url)
                ok = False
                url = session.url

        return PaymentOutput(ok=ok, redirect_url=url)

    @strawberry.mutation(permission_classes=[IsAccessToken])
    def increment_capturer_attribute(self, info: Info, ia_service_name: ImageAPIServiceNames) -> MutationResult:
        access_token = get_token(info=info)
        return MutationResult(ok=LicensingCommonEvent.add_capturer_usage(ia_service_name.value, access_token))
