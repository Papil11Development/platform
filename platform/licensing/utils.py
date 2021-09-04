import hashlib
import uuid
from datetime import timedelta, datetime
from decimal import Decimal
from typing import List, Union, Optional, Literal, Tuple

from django.conf import settings
from stripe import Subscription, Invoice, InvoiceLineItem, SubscriptionItem

from licensing.models import License, Product
from licensing.payment.stripe.api import StripeAPI
from licensing.policies import change_plan_replace_items, downgrade_usage_restricted
from platform_lib.exceptions import LicenseException
from platform_lib.utils import utcnow_with_tz, utcfromtimestamp_with_tz


def prepare_stripe_product_ids(stripe_plan_ids: List[Tuple[str, str]]) -> str:
    """
    Generate sha1 hash based on combination of product and prise ids for product determination

    Parameters
    ----------
    stripe_plan_ids: List[Tuple[str, str]]
        List of tuples with (product_id, price_id)

    Returns
    -------
    str
        Product key
    """
    return hashlib.sha1(str(sorted(stripe_plan_ids)).encode()).hexdigest()


def timestamp_for_send_usage(lic: License, billing_cycle_start: Optional[datetime] = None) -> int:
    """
    Return "start of billing cycle + 20 sec" if the current day is equal billing_cycle_start day,
    else return current day timestamp at 00 hours.
    If billing_cycle_start provided use it as reporting point instead of license time.
     Need for change_plan() because stripe subscription periods can change

    :return: int
    """
    cycle_period = lic.period_in_days

    if settings.TS_GROUP in [gr.name for gr in lic.billing_account.user.groups.all()]:
        customer = StripeAPI.get_customer(lic.billing_account.stripe_customer_id, expand=['test_clock'])

        current_time = utcfromtimestamp_with_tz(customer['test_clock']['frozen_time'])
        if billing_cycle_start is None:
            subscription = StripeAPI(lic.billing_account).get_subscription(lic.subscription_id)
            billing_cycle_start = utcfromtimestamp_with_tz(
                subscription['current_period_end']) - timedelta(days=cycle_period)

    else:
        current_time = utcnow_with_tz()
        if billing_cycle_start is None:
            billing_cycle_start = lic.expiration_date - timedelta(days=cycle_period)

    if billing_cycle_start.day == current_time.day and billing_cycle_start.month == current_time.month:
        return int(billing_cycle_start.timestamp() + 20)

    return int(current_time.replace(hour=00, minute=00, second=00).timestamp())


def get_data(obj_: Union[Subscription, Invoice]) -> List[Union[SubscriptionItem, InvoiceLineItem]]:
    if isinstance(obj_, Subscription):
        return obj_['items']['data']
    elif isinstance(obj_, Invoice):
        return obj_['lines']['data']
    else:
        raise NotImplementedError


def verify_license_plan_change(new_product: Product,
                               lic: License) -> Tuple[bool, Optional[Literal['downgrade', 'upgrade']],
                                                      bool, Optional[str]]:
    if lic.product is None:
        raise LicenseException(f'Internal error: license has not product')

    operation = lic.product.flow_operation(new_product.name)
    replace_items = True if new_product.name in change_plan_replace_items else False
    usage_policy = True
    error_message = None

    if (operation == 'downgrade') and (new_product.name in downgrade_usage_restricted):
        product_meter_attributes = new_product.get_meter_attributes(lic.is_trial, qa=lic.billing_account.is_qa)

        for attribute in lic.meter_attributes:
            prod_attr = next(filter(lambda x: x.title == attribute.title, product_meter_attributes))
            if prod_attr.limit and (prod_attr.limit != -1) and (attribute.gross_uses > prod_attr.limit):
                usage_policy = False
                error_message = "Downgrade is not possible because current uses" \
                                " count more than limit in desired plan"
                break

    if operation is None:
        error_message = "License not support downgrading or upgrading to this plan"

    return bool(operation and usage_policy), operation, replace_items, error_message


def get_channels_item(obj_: Union[Subscription, Invoice]) -> Union[SubscriptionItem, InvoiceLineItem]:
    items = get_data(obj_)
    return next(filter(lambda it: it.get('price', {}).get('metadata', {}).get('title') == 'channels', items), {})


def find_item_by_price(obj_: Union[Subscription, Invoice], price_id: str) -> Union[SubscriptionItem, InvoiceLineItem]:
    items = get_data(obj_)
    return next(filter(lambda it: it.get('price', {}).get('id') == price_id, items), {})


def get_inactive_items(obj_: Union[Subscription, Invoice]) -> List[Union[SubscriptionItem, InvoiceLineItem]]:
    items = get_data(obj_)
    return list(filter(lambda it: it.get('metadata', {}).get('active') == 'false', items))


def cents_to_dollars(number: int) -> Decimal:
    return Decimal(number / 100).quantize(Decimal('.00'))


class TransactionValidator:
    SALT = 'a3930741032043699ea9'

    def __init__(self, signature: str = None):
        self.__signature = signature if signature else str(uuid.uuid4())

    @property
    def signature(self) -> str:
        return self.__signature

    def validate(self, enrypted_signature: str):
        return enrypted_signature == self.encrypt()

    def encrypt(self):
        return hashlib.sha1((self.__signature + self.SALT).encode('utf8')).hexdigest()
