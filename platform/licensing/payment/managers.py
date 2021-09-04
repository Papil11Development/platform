import logging
from datetime import datetime
from functools import lru_cache
from typing import List, Union, Literal, Callable, Type, Tuple, Optional

import stripe
from django.db.models import Q
from django.http import HttpRequest
from stripe import Invoice as StripeInvoice

from licensing.api.v2.types import PaymentSource
from licensing.managers import MeterAttributeManager, BaseLicenseManager
from licensing.models import BillingAccount, Product, WebhookLog, License
from licensing.payment.models import Subscription
from licensing.payment.stripe.api import StripeAPI
from licensing.payment.stripe.events import PaymentMethodEventType, CustomerEvent, InvoiceEventType, \
    SubscriptionEventType, CheckoutEventType, CustomerEventType, InvoiceEvent, SubscriptionEvent, CheckoutEvent, \
    Invoice, PaymentMethodEvent
from licensing.utils import find_item_by_price, get_inactive_items, timestamp_for_send_usage
from licensing.utils import prepare_stripe_product_ids
from platform_lib.data.common_models import MeterAttribute
from platform_lib.exceptions import StripeException, StripeDuplicateWebhook, PaymentMethodNotExist, \
    StripePaymentFailed, CognitiveWebhook
from platform_lib.utils import utcfromtimestamp_with_tz

logger = logging.getLogger(__name__)


class StripeEventManager:
    @classmethod
    def __get_event_class(cls, event_type: str) -> Union[Type[InvoiceEventType],
                                                         Type[SubscriptionEventType],
                                                         Type[CheckoutEventType],
                                                         Type[CustomerEventType],
                                                         Type[PaymentMethodEventType], None]:
        return {
            'customer.created': CustomerEventType,
            'invoice.paid': InvoiceEventType,
            'invoice.payment_failed': InvoiceEventType,
            'checkout.session.completed': CheckoutEventType,
            'customer.subscription.updated': SubscriptionEventType,
            'customer.subscription.deleted': SubscriptionEventType,
            'payment_method.attached': PaymentMethodEventType,
            'payment_method.detached': PaymentMethodEventType
        }.get(event_type)  # type: ignore

    @classmethod
    def __get_handle_func(cls, event_type: Union[InvoiceEventType,
                                                 SubscriptionEventType,
                                                 CheckoutEventType,
                                                 CustomerEventType,
                                                 PaymentMethodEventType]) -> Callable:
        return {
            InvoiceEventType: cls.__handle_invoice_event,
            SubscriptionEventType: cls.__handle_subscription_event,
            CheckoutEventType: cls.__handle_checkout_event,
            CustomerEventType: cls.__handle_customer_event,
            PaymentMethodEventType: cls.__handle_payment_method_event,
        }.get(type(event_type))  # type: ignore

    @classmethod
    def construct_stripe_event(cls, request: HttpRequest) -> Union[InvoiceEvent,
                                                                   SubscriptionEvent,
                                                                   CheckoutEvent,
                                                                   CustomerEvent]:
        signature = request.META['HTTP_STRIPE_SIGNATURE']
        stripe_event = StripeAPI.construct_webhook_event(signature, request.body)

        if WebhookLog.is_exist(stripe_event['id']):
            raise StripeDuplicateWebhook

        # Reject webhooks from Cognitive
        if stripe_event['type'] != 'customer.created':
            customer_id = (stripe_event['data']['object']['customer'] or
                           stripe_event['data']['previous_attributes']['customer'])
            try:
                BillingAccount.objects.get(stripe_customer_id=customer_id)
            except BillingAccount.DoesNotExist:
                raise CognitiveWebhook

        event_class = cls.__get_event_class(stripe_event['type'])
        if event_class is None:
            raise StripeException(f'Not implemented stripe processing event: {stripe_event["type"]}')

        event_type = event_class.from_stripe(stripe_event)
        handle_event_func = cls.__get_handle_func(event_type)
        if handle_event_func is None:
            raise StripeException(f'Not implemented stripe event creation: {type(event_type)}')

        return handle_event_func(stripe_event, event_type)

    @classmethod
    def __handle_customer_event(cls, event: dict, event_type: CustomerEventType) -> CustomerEvent:
        data = event['data']['object']

        return CustomerEvent(
            id=event['id'],
            type=event_type,
            customer_id=data['id'],
            email=data['email'],
            test_clock=data['test_clock'],
            livemode=data['livemode'],
            description=data['description']
        )

    @classmethod
    def __handle_subscription_event(cls, event: dict, event_type: SubscriptionEventType) -> SubscriptionEvent:
        subscription_raw = event['data']['object']
        previous_attr = event['data'].get('previous_attributes', {})

        subscription = Subscription.from_dict(subscription_raw, previous_attributes=previous_attr)

        workspace_id = event['data']['object']['metadata'].get('workspace')
        license_id = event['data']['object']['metadata'].get('license')

        if license_id is not None:
            getter = Q(licenses=license_id)
        elif workspace_id is not None:
            getter = Q(licenses__workspace_id=workspace_id)
        else:
            raise StripeException('Subscription without license or workspace id')

        qa = BillingAccount.objects.get(getter).is_qa

        if workspace_id is None and license_id is None:
            raise StripeException(f'Event without license and workspace id')

        plan_products = [(attribute.product_id, attribute.plan)
                         for attribute in subscription.meter_attributes or []]
        stripe_product_id = prepare_stripe_product_ids(plan_products)  # type: ignore

        try:
            product = Product.get_product_by_stripe_id(
                stripe_product_id,
                qa=qa
            )
        except (Product.DoesNotExist, Product.MultipleObjectsReturned):
            raise StripeException(f'Wrong stripe product combination')

        subscription.enrich_limit_from_product(product=product,
                                               is_trial=subscription_raw['status'] == 'trialing',
                                               qa=qa)

        return SubscriptionEvent(
            id=event['id'],
            type=event_type,
            workspace_id=workspace_id,
            license_id=license_id,
            product=product,
            subscription=subscription
        )

    @classmethod
    def __handle_invoice_event(cls, event: dict, event_type: InvoiceEventType) -> InvoiceEvent:
        def __delete_inactive_sub_items(sub: Subscription, stripe_api_: StripeAPI):
            items = get_inactive_items(sub)
            for item in items:
                stripe_api_.delete_subscription_item(item['id'])

        invoice = event['data']['object']
        subscription_id = invoice['subscription'] or invoice['metadata']['subscription']
        customer_id = invoice['customer']

        account = BillingAccount.objects.get(stripe_customer_id=customer_id)
        stripe_api = StripeAPI(account)

        subscription_raw = stripe_api.get_subscription(subscription_id)
        subscription = Subscription.from_dict(subscription_raw)

        workspace_id = subscription_raw['metadata'].get('workspace')
        license_id = subscription_raw['metadata'].get('license')

        if workspace_id is None and license_id is None:
            raise StripeException(f'Event without license and workspace id')

        raw_payment_attempt = invoice['next_payment_attempt']
        next_payment_attempt = utcfromtimestamp_with_tz(raw_payment_attempt) if raw_payment_attempt else None

        if invoice['paid'] and subscription_raw['status'] != 'canceled':
            __delete_inactive_sub_items(subscription_raw, stripe_api)

        return InvoiceEvent(
            id=event['id'],
            invoice=Invoice(invoice['id'], invoice['paid'], invoice['total'], next_payment_attempt),
            type=event_type,
            workspace_id=workspace_id,
            license_id=license_id,
            subscription=subscription
        )

    @classmethod
    def __handle_checkout_event(cls, event: dict, event_type: CheckoutEventType):

        if event_type == CheckoutEventType.setup_event:
            workspace_id = event['data']['object']['metadata'].get('workspace')
            license_id = event['data']['object']['metadata'].get('license')
        else:
            raise NotImplementedError

        return CheckoutEvent(
            id=event['id'],
            type=event_type,
            workspace_id=workspace_id,
            license_id=license_id
        )

    @classmethod
    def __handle_payment_method_event(cls, event: dict, event_type: PaymentMethodEventType) -> PaymentMethodEvent:
        customer_id = event['data']['object']['customer'] or event['data']['previous_attributes']['customer']
        payment_method_id = event['data']['object']['id']

        return PaymentMethodEvent(
            id=event['id'],
            type=event_type,
            customer_id=customer_id,
            payment_method_id=payment_method_id
        )

    @staticmethod
    def __enrich_limit_from_product(meter_attributes: List[MeterAttribute],
                                    product: Product,
                                    is_trial: bool = False,
                                    qa: bool = False):
        for attribute in meter_attributes:
            attribute.limit = product.get_meter_attribute(attr_name=attribute.title, is_trial=is_trial, qa=qa).limit


class PaymentManager:
    @staticmethod
    def is_alive_subscription(payment_source: PaymentSource, lic: License) -> bool:
        if payment_source == PaymentSource.stripe:
            stripe_api = StripeAPI(lic.billing_account)
            return stripe_api.is_alive_subscription(lic.subscription_id)

        raise NotImplementedError

    @staticmethod
    def cancel_subscription(payment_source: PaymentSource, lic: License):
        if payment_source == PaymentSource.stripe:
            stripe_api = StripeAPI(lic.billing_account)
            response = stripe_api.cancel_subscription(lic.subscription_id)
            if not response.get('cancel_at_period_end'):
                raise StripeException(f'Failed to cancel subscription')

    @staticmethod
    def activate_subscription(payment_source: PaymentSource, lic: License):
        if payment_source == PaymentSource.stripe:
            stripe_api = StripeAPI(lic.billing_account)
            subscription = stripe_api.get_subscription(lic.subscription_id)
            if subscription['status'] not in ['canceled', 'incomplete', 'incomplete_expired']:
                response = stripe_api.activate_subscription(lic.subscription_id)
                if response.get('cancel_at_period_end'):
                    raise StripeException(f'Failed to activate subscription')
            elif subscription['status'] in ['incomplete', 'incomplete_expired']:
                pass
            else:
                customer = StripeAPI.get_customer(lic.billing_account.stripe_customer_id)
                exist_payment_method = customer['invoice_settings']['default_payment_method']
                if exist_payment_method:
                    subscription_invoices = stripe_api.get_invoices_with_total(lic.subscription_id)

                    debt_invoices = list(filter(lambda it: it['status'] in ['draft', 'uncollectible', 'open'],
                                                subscription_invoices))
                    if debt_invoices:
                        raise StripeException("Pay previous invoices before activate subscription")

                    metadata = {'workspace': lic.workspace.id} if lic.workspace else {'license': lic.id}
                    items = [{
                        'price': attribute.plan,
                        'metadata': {'active': 'true'}
                    } for attribute in lic.meter_attributes]

                    subscription_raw = stripe_api.create_subscription(lic.billing_account.stripe_customer_id,
                                                                      items,
                                                                      metadata)
                    subscription = Subscription.from_dict(subscription_raw)
                    subscription.enrich_limit_from_product(lic.product, lic.is_trial)

                    BaseLicenseManager.update_license(lic=lic,
                                                      subscription_id=subscription.id,
                                                      expiration_date=subscription.expiration_date,
                                                      cancel_at_period_end=subscription.cancel_at_period_end,
                                                      status=subscription.status,
                                                      metered_attributes=subscription.meter_attributes)

                    if subscription_raw['status'] == 'incomplete':
                        raise StripeException("Invoice has not been paid")
                else:
                    raise PaymentMethodNotExist('Payment method does not configured')

    @staticmethod
    @lru_cache(maxsize=32)
    def get_price(payment_source: PaymentSource, price_id, user: BillingAccount) -> dict:
        if payment_source == PaymentSource.stripe:
            return StripeAPI(user).get_price(price_id)

        raise NotImplementedError

    @staticmethod
    def change_plan(payment_source: PaymentSource,
                    lic: License,
                    meter_attributes_plans: dict,
                    operation: Literal['upgrade', 'downgrade'],
                    replace_items: Optional[bool] = False) -> Optional[dict]:

        def report_usage(lic_: License, new_subscription_: Subscription, plan_name_: str, price_id_: str):
            stripe_item_id_ = find_item_by_price(new_subscription_, price_id_).get('id')
            meter_atr_ = getattr(lic_, plan_name_)

            _, uses_ = MeterAttributeManager.prepare_meter_info_for_report(lic_, meter_atr_)

            usage_timestamp_ = timestamp_for_send_usage(
                lic_,
                datetime.fromtimestamp(new_subscription['current_period_start'])
            )

            stripe_api.send_usage_records(stripe_item_id_,
                                          uses_,
                                          'set',
                                          usage_timestamp_)

        if payment_source == PaymentSource.stripe:
            new_items = []
            old_items = []

            stripe_api = StripeAPI(lic.billing_account)
            subscription = stripe_api.get_subscription(lic.subscription_id)

            for plan_name, price_id in meter_attributes_plans.items():
                exist_stripe_item = find_item_by_price(subscription, price_id)

                new_item = {'id': exist_stripe_item['id']} if exist_stripe_item else {'price': price_id}
                new_items += [{**new_item, 'metadata': {'active': 'true'}}]

                old_item = BaseLicenseManager.get_meter_attribute_in_stripe_format(lic, plan_name)

                if old_item is not None:
                    old_item.update({'metadata': {'active': 'false'}})
                    old_items.append(old_item)

            new_subscription = stripe_api.modify_subscription(lic.subscription_id,
                                                              # form new items list with old items
                                                              # for license with stacking behavior
                                                              new_items if replace_items else [*new_items, *old_items],
                                                              int(lic.expiration_date.timestamp()),
                                                              proration_behavior='create_prorations')

            # remove old items if license behavior demands it
            if replace_items:
                for old_item in old_items:
                    stripe_api.delete_subscription_item(old_item['id'])

            # report usage even in downgrade if license behavior implies removing old items
            if operation == 'downgrade' and replace_items:
                for plan_name, price_id in meter_attributes_plans.items():
                    report_usage(lic, new_subscription, plan_name, price_id)

            # report usage if license upgrading
            if operation == 'upgrade':
                for plan_name, price_id in meter_attributes_plans.items():
                    report_usage(lic, new_subscription, plan_name, price_id)

            return new_subscription

        raise NotImplementedError

    @staticmethod
    def __collapse_invoices(lic: License, stripe_api: StripeAPI) -> Tuple[Optional[str],
                                                                          Optional[str],
                                                                          List[StripeInvoice]]:
        """
        Return tuple with invoice_id for pay, new_invoice_id, old_invoices.
        Variables can be null

        :return: tuple
        """
        def __get_invoices_for_collapse(invoices: List[StripeInvoice]) -> List[StripeInvoice]:
            return list(filter(lambda it: it['status'] in ['draft', 'uncollectible', 'open'], invoices))

        old_invoices = stripe_api.get_invoices_with_total(lic.subscription_id)
        invoices_for_collapse = __get_invoices_for_collapse(old_invoices)

        invoices_for_collapse_count = len(invoices_for_collapse)
        if invoices_for_collapse_count == 0:
            return None, None, []
        elif invoices_for_collapse_count == 1:
            return invoices_for_collapse[0]['id'], None, []

        new_invoice = stripe_api.create_empty_invoice(metadata={**invoices_for_collapse[0]['metadata'],
                                                                'subscription': lic.subscription_id})

        for old_invoice in invoices_for_collapse:
            invoice_items = old_invoice['lines']['data']
            for item in invoice_items:
                if item['amount'] != 0:
                    stripe_api.create_invoice_item(invoice_id=new_invoice['id'],
                                                   period=item['period'],
                                                   metadata=item['metadata'],
                                                   description=item['description'],
                                                   currency=item['currency'],
                                                   amount=item['amount']
                                                   )

        stripe_api.finalize_invoice(new_invoice['id'], auto_advance=False)

        return new_invoice['id'], new_invoice['id'], invoices_for_collapse

    @classmethod
    def try_pay_invoice(cls, payment_source: PaymentSource, lic: License) -> stripe.Invoice:
        if payment_source == PaymentSource.stripe:
            customer = StripeAPI.get_customer(lic.billing_account.stripe_customer_id)
            if customer['invoice_settings']['default_payment_method']:
                stripe_api = StripeAPI(lic.billing_account)
                invoice_id_for_pay, new_invoice_id, old_invoices = cls.__collapse_invoices(lic, stripe_api)

                if invoice_id_for_pay is None:
                    raise StripeException('There are no open invoices')

                try:
                    invoice = stripe_api.pay_invoice(invoice_id_for_pay)
                    for old_invoice in old_invoices:
                        if old_invoice['status'] == 'draft':
                            stripe_api.finalize_invoice(invoice_id=old_invoice['id'], auto_advance=False)

                        stripe_api.void_invoice(invoice_id=old_invoice['id'])
                except StripeException:
                    if new_invoice_id:
                        stripe_api.void_invoice(invoice_id=new_invoice_id)
                    raise StripePaymentFailed(f"Invoice has not been paid")

                return invoice

            else:
                raise PaymentMethodNotExist('Payment method does not configured')
        else:
            raise NotImplementedError

    @staticmethod
    def update_payment_method(billing_account: BillingAccount,
                              success_url: str,
                              cancel_url: str) -> stripe.checkout.Session:
        stripe_api = StripeAPI(billing_account)
        return stripe_api.create_session(customer_id=billing_account.stripe_customer_id,
                                         success_url=success_url,
                                         cancel_url=cancel_url,
                                         mode='setup')
