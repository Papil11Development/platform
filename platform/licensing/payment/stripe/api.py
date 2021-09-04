from typing import Optional, Union, List, Literal

import stripe
from django.conf import settings
from django.db import transaction
from stripe.error import StripeError

from licensing.models import BillingAccount
from licensing.payment.stripe.utils import stripe_error_handler
from platform_lib.exceptions import StripeException

stripe.api_version = settings.STRIPE_API_VERSION


@stripe_error_handler
class StripeAPI:
    def __init__(self, account: BillingAccount):
        self.__api_key = self.__get_api_key(account)
        self.account = account

    def get_or_create_customer(self) -> str:
        if self.account.stripe_customer_id:
            return self.account.stripe_customer_id

        customer = stripe.Customer.create(email=self.account.username, api_key=self.__api_key,
                                          metadata={'username': self.account.username})

        with transaction.atomic():
            lock_account = BillingAccount.lock_account(self.account)
            lock_account.stripe_customer_id = customer['id']  # store id to not duplicate customers
            lock_account.save()

        return customer['id']

    def create_session(self,
                       customer_id: str,
                       success_url: str,
                       cancel_url: str,
                       mode: str,
                       metadata: Optional[dict] = None,
                       items: Optional[List[dict]] = None,
                       coupon_id: Optional[str] = None) -> stripe.checkout.Session:

        session_params = {
            'customer': customer_id,
            'payment_method_types': ['card'],
            'success_url': success_url,
            'cancel_url': cancel_url,
            'mode': mode,
            'metadata': metadata,  # To link session with platform
            'api_key': self.__api_key
        }

        if mode == 'subscription' and items is not None:
            session_params.update({'subscription_data': {'metadata': metadata},  # To link subscription with platform
                                   'line_items': items})  # type: ignore
            if coupon_id:
                session_params.update({'discounts': [{'coupon': coupon_id}]})  # type: ignore

        return stripe.checkout.Session.create(**session_params)

    def create_subscription(self,
                            customer_id: str,
                            items: List[dict],
                            metadata: dict,
                            trial_period_days: Optional[str] = None) -> stripe.Subscription:

        query_params = {
            'customer': customer_id,
            'items': items,
            'metadata': metadata,  # To link session with platform
            'api_key': self.__api_key
        }

        if trial_period_days:
            query_params.update({'trial_period_days': trial_period_days,
                                 'cancel_at_period_end': True})  # type: ignore

        return stripe.Subscription.create(**query_params)

    def get_subscription(self, subscription_id: str) -> stripe.Subscription:
        return stripe.Subscription.retrieve(subscription_id, api_key=self.__api_key)

    def cancel_subscription(self, subscription_id: str) -> stripe.Subscription:
        return stripe.Subscription.modify(subscription_id, cancel_at_period_end=True, api_key=self.__api_key)

    def activate_subscription(self, subscription_id: str) -> stripe.Subscription:
        return stripe.Subscription.modify(subscription_id, cancel_at_period_end=False, api_key=self.__api_key)

    def get_customer_payment_methods(self, customer_id: str) -> List[stripe.PaymentMethod]:
        return stripe.PaymentMethod.list(customer=customer_id, type="card", api_key=self.__api_key)

    def modify_subscription(self,
                            subscription_id: str,
                            items: list,
                            proration_date: int,
                            metadata: Optional[dict] = None,
                            proration_behavior: Optional[str] = None) -> stripe.Subscription:
        return stripe.Subscription.modify(subscription_id,
                                          api_key=self.__api_key,
                                          items=items,
                                          metadata=metadata,
                                          proration_date=proration_date,
                                          proration_behavior=proration_behavior)

    def stop_trial_for_subscription(self, subscription_id: str) -> stripe.Subscription:
        return stripe.Subscription.modify(subscription_id, api_key=self.__api_key, trial_end='now')

    def delete_subscription_item(self, si_id: str) -> stripe.SubscriptionItem:
        return stripe.SubscriptionItem.delete(si_id, api_key=self.__api_key, clear_usage='true')

    def setup_default_payment_method(self, customer_id: str, payment_method_id: str) -> stripe.Customer:
        return stripe.Customer.modify(customer_id, invoice_settings={"default_payment_method": payment_method_id},
                                      api_key=self.__api_key)

    def detach_payment_method(self, payment_method_id: str) -> stripe.PaymentMethod:
        return stripe.PaymentMethod.detach(payment_method_id, api_key=self.__api_key)

    def get_setup_intent(self, setup_intent_id: str) -> stripe.Subscription:
        return stripe.SetupIntent.retrieve(setup_intent_id, api_key=self.__api_key)

    def is_alive_subscription(self, subscription_id: str) -> bool:
        subscription = self.get_subscription(subscription_id)
        return subscription['status'] not in ['canceled']

    def send_usage_records(self, si_id: str, quantity: int, action: Literal['set', 'increment'],
                           timestamp: Optional[int] = None) -> stripe.UsageRecord:
        return stripe.SubscriptionItem.create_usage_record(si_id, api_key=self.__api_key, quantity=quantity,
                                                           action=action, timestamp=timestamp if timestamp else 'now')

    def get_session(self, session_id: str) -> stripe.checkout.Session:
        return stripe.checkout.Session.retrieve(session_id, api_key=self.__api_key)

    def get_payment_method(self, pm_id: str) -> stripe.PaymentMethod:
        return stripe.PaymentMethod.retrieve(pm_id, api_key=self.__api_key)

    def create_empty_invoice(self, metadata: dict) -> stripe.Invoice:
        return stripe.Invoice.create(customer=self.account.stripe_customer_id, pending_invoice_items_behavior='exclude',
                                     auto_advance=False, metadata=metadata, api_key=self.__api_key)

    def get_invoice(self, invoice_id: str) -> stripe.Invoice:
        return stripe.Invoice.retrieve(invoice_id, api_key=self.__api_key)

    def get_invoices_with_total(self, subscription_id: str, total_more: int = 0) -> List[stripe.Invoice]:
        invoices_by_sub = stripe.Invoice.search(
            query=f'subscription:"{subscription_id}" AND total>{total_more}',
            limit=100,
            api_key=self.__api_key
        )

        return invoices_by_sub['data']

    def get_upcoming_invoice(self, subscription_id: str) -> stripe.Invoice:
        return stripe.Invoice.upcoming(
            customer=self.account.stripe_customer_id,
            subscription=subscription_id,
            api_key=self.__api_key
        )

    def pay_invoice(self, invoice_id: str) -> stripe.Invoice:
        return stripe.Invoice.pay(invoice_id, api_key=self.__api_key, expand=['subscription'])

    def void_invoice(self, invoice_id: str) -> stripe.Invoice:
        return stripe.Invoice.void_invoice(invoice_id, api_key=self.__api_key)

    def finalize_invoice(self, invoice_id: str, auto_advance: bool) -> stripe.Invoice:
        return stripe.Invoice.finalize_invoice(invoice_id, auto_advance=auto_advance, api_key=self.__api_key)

    def create_invoice_item(self, invoice_id: str, period: dict, description: str,
                            metadata: dict, amount: int, currency: str):
        return stripe.InvoiceItem.create(
            invoice=invoice_id,
            customer=self.account.stripe_customer_id,
            metadata=metadata,
            description=description,
            period=period,
            amount=amount,
            currency=currency,
            api_key=self.__api_key
        )

    def get_price(self, plan_id: str) -> stripe.Price:
        return stripe.Price.retrieve(plan_id, api_key=self.__api_key, expand=['tiers'])

    def get_product(self, product_id: str) -> stripe.Product:
        return stripe.Product.retrieve(product_id, api_key=self.__api_key)

    @staticmethod
    def get_customer(customer_id: str,
                     expand: Optional[List[Literal['test_clock', 'invoice_settings.default_payment_method',
                                                   'subscriptions']]] = None) -> stripe.Customer:
        if expand is None:
            expand = []
        for token in [settings.STRIPE_LIVE_TOKEN, settings.STRIPE_TEST_TOKEN]:
            try:
                return stripe.Customer.retrieve(customer_id, api_key=token, expand=expand)
            except StripeError as ex:
                error = str(ex)

        raise StripeException(error)

    @staticmethod
    def construct_webhook_event(signature: str, payload: Union[str, bytes]) -> stripe.Event:
        for webhook_secret, token in [(settings.STRIPE_LIVE_WEBHOOK_SECRET, settings.STRIPE_LIVE_TOKEN),
                                      (settings.STRIPE_TEST_WEBHOOK_SECRET, settings.STRIPE_TEST_TOKEN)]:
            try:
                return stripe.Webhook.construct_event(payload, signature, webhook_secret, api_key=token)
            except StripeError as ex:
                error = str(ex)

        raise StripeException(error)

    @staticmethod
    def get_public_key(account: BillingAccount) -> str:
        if settings.PAYMENT_MODE == 'test' or account.is_qa:
            return settings.STRIPE_TEST_PUBLIC_TOKEN

        return settings.STRIPE_LIVE_PUBLIC_TOKEN

    @staticmethod
    def __get_api_key(account: Optional[BillingAccount] = None) -> str:
        if settings.PAYMENT_MODE == 'test' or (account and account.is_qa):
            return settings.STRIPE_TEST_TOKEN

        return settings.STRIPE_LIVE_TOKEN
