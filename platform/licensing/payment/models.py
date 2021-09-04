import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from stripe.stripe_object import StripeObject

from platform_lib.data.common_models import MeterAttribute, CommonModel, SubscriptionStatus
from platform_lib.utils import utcfromtimestamp_with_tz
from licensing.models import Product

logger = logging.getLogger(__name__)


@dataclass
class Subscription(CommonModel):
    id: str
    status: SubscriptionStatus
    previous_attributes: dict
    expiration_date: Optional[datetime] = None
    meter_attributes: Optional[List[MeterAttribute]] = None
    cancel_at_period_end: bool = False

    def serialize(self, name, obj):
        if isinstance(obj, datetime):
            obj = obj.isoformat()
        elif isinstance(obj, MeterAttribute):
            obj = obj.to_dict()
        elif isinstance(obj, StripeObject):
            obj = obj.serialize({})
        else:
            obj = super().serialize(name, obj)
        return obj

    @classmethod
    def from_dict(cls, subscription_raw: dict, previous_attributes: Optional[dict] = None) -> 'Subscription':
        plans = cls.__get_active_plans(subscription_raw)
        meter_attributes = cls.__meter_attributes(plans)
        subscription_id = subscription_raw['id']

        subscription_expiration_date = (utcfromtimestamp_with_tz(subscription_raw['current_period_end']) if
                                        subscription_raw['current_period_end'] else None)

        status = SubscriptionStatus(subscription_raw['status'])

        if previous_attributes is None:
            previous_attributes = {}

        if 'cancel_at_period_end' in previous_attributes:
            subscription_expiration_date = None
        elif subscription_raw['status'] == 'canceled':
            subscription_expiration_date = subscription_raw['cancel_at'] or subscription_raw['canceled_at']
            subscription_expiration_date = utcfromtimestamp_with_tz(subscription_expiration_date)

        return Subscription(
            subscription_id,
            status,
            previous_attributes,
            subscription_expiration_date,
            meter_attributes,
            subscription_raw['cancel_at_period_end']
        )

    @staticmethod
    def __get_active_plans(subscription: dict) -> dict:
        """Return plans in format:
           {
             "plan_name": plan_object,
             ...
           }
        """
        sub_items = subscription['items']['data']

        return {
            item['price']['metadata']['title']: item for item in sub_items if
            item['metadata']['active'] == 'true'
        }

    @staticmethod
    def __meter_attributes(plans: dict) -> List[MeterAttribute]:
        return [MeterAttribute(
            title=name,
            plan=plan['price']['id'],
            stripe_item_id=plan['id'],
            product_id=plan['price']['product']
        ) for name, plan in plans.items() if plan]

    def enrich_limit_from_product(self,
                                  product: Product,
                                  is_trial: bool = False,
                                  qa: bool = False):
        for attribute in self.meter_attributes or []:
            attribute.limit = product.get_meter_attribute(attr_name=attribute.title, is_trial=is_trial, qa=qa).limit
