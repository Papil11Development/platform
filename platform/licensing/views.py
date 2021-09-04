import logging
import traceback
from typing import Union, Optional, Callable, Dict, Type, Any

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from licensing.managers import BaseLicenseManager
from licensing.models import WebhookLog, WorkspaceLicense
from licensing.payment.managers import StripeEventManager
from licensing.payment.stripe.api import StripeAPI
from licensing.payment.stripe.events import InvoiceEventType, SubscriptionEventType, CheckoutEventType, \
    CustomerEventType, InvoiceEvent, SubscriptionEvent, CheckoutEvent, CustomerEvent, PaymentMethodEventType, \
    PaymentMethodEvent
from licensing.policies import rotate_meter_attribute_after_cycle
from licensing.tasks import send_usage_records
from platform_lib.data.common_models import SubscriptionStatus
from platform_lib.exceptions import StripeException, StripeDuplicateWebhook, CognitiveWebhook
from user_domain.managers import WorkspaceManager, LoginManager

logger = logging.getLogger(__name__)


@method_decorator([csrf_exempt], 'dispatch')
class StripeWebhook(View):
    def post(self, request):
        try:
            event = StripeEventManager.construct_stripe_event(request)
        except StripeDuplicateWebhook:
            logger.warning(f'Stripe webhook duplicate')
            return HttpResponse(status=200)  # send 200 to Stripe to not resend the webhook
        except CognitiveWebhook:
            logger.warning(f'Webhook from Cognitive')
            return HttpResponse(status=200)  # send 200 to Stripe to not resend the webhook
        except StripeException:
            logger.error(f'Stripe error: {traceback.format_exc()}')
            return HttpResponse(status=500)
        except Exception:
            logger.error(f'Internal error: {traceback.format_exc()}')
            return HttpResponse(status=500)

        try:
            handle_func = self.event_handle_mapping[type(event.type)]
        except KeyError:
            logger.error(f'Event type does not supported: {event.type}')
            return HttpResponse(status=500)

        handle_func(event)

        WebhookLog.from_stripe(event.id, event.to_dict())  # log event id to process it once

        event_message = self._generate_message_by_event(event)
        logger.info(event_message)
        return HttpResponse(status=200)

    @property
    def event_handle_mapping(self) -> Dict[Union[Type[SubscriptionEventType],
                                                 Type[InvoiceEventType],
                                                 Type[CheckoutEventType],
                                                 Type[CustomerEventType],
                                                 Type[PaymentMethodEventType]], Callable]:
        return {
            SubscriptionEventType: self.handle_subscription_event,
            InvoiceEventType: self.handle_invoice_event,
            CheckoutEventType: self.handle_checkout_event,
            CustomerEventType: self.handle_customer_event,
            PaymentMethodEventType: self.handle_payment_method_event,
        }

    @staticmethod
    def handle_payment_method_event(event: PaymentMethodEvent):
        billing_account = event.get_billing_account()

        def delete_exist_payment_method(stripe_api_: StripeAPI, customer_: dict):
            exist_payment_method_ = customer_['invoice_settings']['default_payment_method']
            if exist_payment_method_:
                stripe_api_.detach_payment_method(exist_payment_method_)

        def try_to_activate_subscriptions(stripe_api_: StripeAPI, customer_: dict):
            subscriptions = customer_['subscriptions']['data']

            for subscription in subscriptions:
                if subscription['cancel_at_period_end']:
                    stripe_api_.activate_subscription(subscription['id'])

        def try_to_cancel_subscriptions(stripe_api_: StripeAPI, customer_: dict):
            subscriptions = customer_['subscriptions']['data']

            for subscription in subscriptions:
                if not subscription['cancel_at_period_end']:
                    stripe_api_.cancel_subscription(subscription['id'])

        def try_to_activate_workspace(lic_: WorkspaceLicense):
            if lic_.status not in [SubscriptionStatus.UNPAID.value, SubscriptionStatus.CANCELED.value]:
                WorkspaceManager.activate_workspace(lic_.workspace)  # type: ignore

        customer = StripeAPI.get_customer(billing_account.stripe_customer_id, ['subscriptions'])
        stripe_api = StripeAPI(billing_account)

        if event.type is PaymentMethodEventType.payment_method_attached:
            delete_exist_payment_method(stripe_api, customer)
            stripe_api.setup_default_payment_method(event.customer_id, event.payment_method_id)
            try_to_activate_subscriptions(stripe_api, customer)

            for lic in billing_account.licenses.filter(workspace_id__isnull=False):  # type: Any
                try_to_activate_workspace(lic)

        elif event.type is PaymentMethodEventType.payment_method_detached:
            payment_methods = stripe_api.get_customer_payment_methods(customer_id=event.customer_id)

            # Check payment methods count for verifying card update case. User can have only one method
            if len(payment_methods) == 0:
                try_to_cancel_subscriptions(stripe_api, customer)

                for lic in billing_account.licenses.filter(workspace_id__isnull=False).\
                        exclude(config__status=SubscriptionStatus.TRIALING):
                    send_usage_records(license_id=lic.id)
                    WorkspaceManager.deactivate_workspace(lic.workspace)

    @staticmethod
    def handle_customer_event(event: CustomerEvent):
        if not event.livemode and event.test_clock:  # only for staging
            from socket import gethostname

            host = gethostname()
            staging_branch = '-'.join(host.split('-')[2:-2])

            if event.description == staging_branch:
                with transaction.atomic():
                    LoginManager.registration_qa_account(
                        email=event.email if event.email else settings.DEFAULT_QA_USER,
                        password=settings.DEFAULT_QA_PASSWORD,
                        customer_id=event.customer_id,
                        with_test_clock=True
                    )

    @staticmethod
    def handle_checkout_event(event: CheckoutEvent):
        pass

    @staticmethod
    def handle_invoice_event(event: InvoiceEvent):
        if event.type in [InvoiceEventType.subscription_cycle, InvoiceEventType.manual]:
            lic = event.get_license()
            workspace = event.get_workspace()

            if lic is None:
                raise StripeException('Subscription without license')

            BaseLicenseManager.update_next_payment_attempt(lic, payment_attempt=event.invoice.next_payment_attempt)

            if event.invoice.paid:
                # nullify all uses in the subscription because user has paid for them
                if lic is not None and lic.product is not None and \
                        lic.product.name in rotate_meter_attribute_after_cycle:
                    with transaction.atomic():
                        BaseLicenseManager.zero_metered_attributes(lic)

                if event.invoice.total != 0:
                    if workspace is not None and lic.status != 'canceled':
                        WorkspaceManager.activate_workspace(workspace)

        elif event.type in [InvoiceEventType.subscription_create]:
            if (workspace := event.get_workspace()) and event.invoice.paid:
                WorkspaceManager.activate_workspace(workspace)
        else:
            pass

    @staticmethod
    def handle_subscription_event(event: SubscriptionEvent):
        lic = event.get_license()
        workspace = event.get_workspace()
        event_sub = event.subscription

        if lic is None:
            raise StripeException('Subscription without license')

        if workspace is not None:
            if event_sub.previous_attributes.get('status') == 'trialing':
                customer = StripeAPI.get_customer(lic.billing_account.stripe_customer_id)
                if not customer['invoice_settings']['default_payment_method']:
                    WorkspaceManager.deactivate_workspace(workspace)
            if event_sub.status == SubscriptionStatus.UNPAID:
                send_usage_records(license_id=lic.id)
                WorkspaceManager.deactivate_workspace(workspace)
            elif event_sub.status == SubscriptionStatus.CANCELED:
                WorkspaceManager.deactivate_workspace(workspace)

        BaseLicenseManager.update_license(lic=lic,
                                          subscription_id=event_sub.id,
                                          expiration_date=event_sub.expiration_date,
                                          cancel_at_period_end=event_sub.cancel_at_period_end,
                                          status=event_sub.status,
                                          metered_attributes=event_sub.meter_attributes,
                                          product=event.product)

    @classmethod
    def _generate_message_by_event(cls, event: Union[InvoiceEvent,
                                                     SubscriptionEvent,
                                                     CheckoutEvent,
                                                     CustomerEvent,
                                                     PaymentMethodEvent]) -> Optional[str]:

        event_message = None
        id_place_holder = None

        if (id_ := getattr(event, 'workspace_id', None)) is not None:
            id_place_holder = f'workspace "{id_}"'
        elif (id_ := getattr(event, 'license_id', None)) is not None:
            id_place_holder = f'license "{id_}"'
        elif (id_ := getattr(event, 'customer_id', None)) is not None:
            id_place_holder = f'{getattr(event, "payment_method_id", None)} for customer "{id_}"'

        if isinstance(event.type, InvoiceEventType):
            if event.type is InvoiceEventType.subscription_cycle:
                event_message = f'Invoice with type subscription_cycle in {id_place_holder} successfully handled!'
            else:
                event_message = f'Invoice in {id_place_holder} successfully handled!'

        elif isinstance(event.type, SubscriptionEventType):
            if event.type is SubscriptionEventType.customer_subscription_updated:
                action = 'updated'
            else:
                action = 'deactivated'

            event_message = f'Subscription in {id_place_holder} successfully {action}!'

        elif isinstance(event.type, PaymentMethodEventType):
            if event.type is PaymentMethodEventType.payment_method_attached:
                event_message = f'Card {id_place_holder} successfully attached!'
            if event.type is PaymentMethodEventType.payment_method_detached:
                event_message = f'Card {id_place_holder} successfully detached!'

        elif isinstance(event.type, CheckoutEventType):
            event_message = f'Checkout event type successfully handled!'

        elif isinstance(event.type, CustomerEventType):
            event_message = f'Customer create successfully handled!'

        return event_message
