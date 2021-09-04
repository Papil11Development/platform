from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from licensing.models import License, BillingAccount, Product
from licensing.payment.models import Subscription
from platform_lib.data.common_models import CommonModel
from platform_lib.exceptions import StripeException
from user_domain.managers import WorkspaceManager
from user_domain.models import Workspace


class StripeTypeEnum(ABC):

    @classmethod
    @abstractmethod
    def from_stripe(cls, event: dict):
        pass


class SubscriptionEventType(Enum):
    __metaclass__ = StripeTypeEnum

    customer_subscription_updated = 'customer.subscription.updated'
    customer_subscription_deleted = 'customer.subscription.deleted'

    @classmethod
    def from_stripe(cls, event: dict) -> 'SubscriptionEventType':
        return cls(event['type'])


class CheckoutEventType(Enum):
    __metaclass__ = StripeTypeEnum

    setup_event = 'setup_event'

    @classmethod
    def from_stripe(cls, event: dict) -> 'CheckoutEventType':
        output = None

        if event['type'] == 'checkout.session.completed':
            mode = event['data']['object']['mode']
            status = event['data']['object']['status']
            if mode == 'setup' and status == 'complete':
                output = cls.setup_event

        if output is None:
            raise StripeException(f'Unknown event type "{event["type"]}"')

        return output


class PaymentMethodEventType(Enum):
    __metaclass__ = StripeTypeEnum

    payment_method_attached = 'payment_method.attached'
    payment_method_detached = 'payment_method.detached'

    @classmethod
    def from_stripe(cls, event: dict) -> 'PaymentMethodEventType':
        return cls(event['type'])


class InvoiceEventType(Enum):
    __metaclass__ = StripeTypeEnum

    invoice_paid = 'invoice.paid'
    invoice_payment_failed = 'invoice.payment_failed'
    subscription_cycle = 'subscription_cycle'
    subscription_create = 'subscription_create'
    manual = 'manual'

    @classmethod
    def from_stripe(cls, event: dict) -> 'InvoiceEventType':
        billing_reason = event['data']['object'].get('billing_reason')
        if billing_reason == 'subscription_cycle':
            return cls.subscription_cycle
        elif billing_reason == 'subscription_create':
            return cls.subscription_create
        elif billing_reason == 'manual':
            return cls.manual
        return cls(event['type'])


class CustomerEventType(Enum):
    __metaclass__ = StripeTypeEnum

    customer_created = 'customer.created'

    @classmethod
    def from_stripe(cls, event: dict) -> 'CustomerEventType':
        return cls(event['type'])


@dataclass
class Invoice(CommonModel):
    id: str
    paid: bool
    total: int
    next_payment_attempt: Optional[datetime] = None

    def serialize(self, name, obj):
        if isinstance(obj, datetime):
            obj = obj.isoformat()
        else:
            obj = super().serialize(name, obj)
        return obj


class StripeEvent(CommonModel, ABC):
    @abstractmethod
    def get_license(self):
        raise NotImplementedError

    @abstractmethod
    def get_workspace(self):
        raise NotImplementedError


@dataclass
class InvoiceEvent(StripeEvent):
    """Contains payment webhook information needed for licensing"""
    id: str  # webhook event id
    type: InvoiceEventType
    invoice: Invoice
    license_id: Optional[str]
    workspace_id: Optional[str]
    subscription: Optional[Subscription] = None

    def serialize(self, name, obj):
        if isinstance(obj, InvoiceEventType):
            obj = obj.value
        elif name == 'subscription':
            obj = self.subscription.serialize(name, obj)
        elif name == 'invoice':
            obj = self.invoice.serialize(name, obj)
        else:
            obj = super().serialize(name, obj)
        return obj

    def get_license(self) -> Optional[License]:
        if self.workspace_id is not None:
            return License.objects.get(workspace_id=self.workspace_id)
        if self.license_id is not None:
            return License.objects.get(id=self.license_id)
        return None

    def get_workspace(self) -> Optional[Workspace]:
        return WorkspaceManager.get_workspace(workspace_id=self.workspace_id) if self.workspace_id else None


@dataclass
class SubscriptionEvent(StripeEvent):
    """Contains stripe webhook information needed for update subscription"""
    id: str  # webhook event id
    type: SubscriptionEventType
    subscription: Subscription
    product: Product
    license_id: Optional[str]
    workspace_id: Optional[str]

    def serialize(self, name, obj):
        if isinstance(obj, SubscriptionEventType):
            obj = obj.value
        elif isinstance(obj, Product):
            obj = str(obj.id)
        elif name == 'subscription':
            obj = self.subscription.serialize(name, obj)
        else:
            obj = super().serialize(name, obj)
        return obj

    def get_license(self) -> Optional[License]:
        if self.workspace_id is not None:
            return License.objects.get(workspace_id=self.workspace_id)
        if self.license_id is not None:
            return License.objects.get(id=self.license_id)
        return None

    def get_workspace(self) -> Optional[Workspace]:
        return WorkspaceManager.get_workspace(workspace_id=self.workspace_id) if self.workspace_id else None


@dataclass
class CheckoutEvent(StripeEvent):
    """Contains stripe webhook information about checkout actions"""
    id: str  # webhook event id
    type: CheckoutEventType
    license_id: Optional[str]
    workspace_id: Optional[str]

    def serialize(self, name, obj):
        if isinstance(obj, CheckoutEventType):
            obj = obj.value
        else:
            obj = super().serialize(name, obj)
        return obj

    def get_license(self) -> Optional[License]:
        if self.workspace_id is not None:
            return License.objects.get(workspace_id=self.workspace_id)
        if self.license_id is not None:
            return License.objects.get(id=self.license_id)
        return None

    def get_workspace(self) -> Optional[Workspace]:
        return WorkspaceManager.get_workspace(workspace_id=self.workspace_id) if self.workspace_id else None


@dataclass
class PaymentMethodEvent(StripeEvent):
    """Contains stripe webhook information about payment method actions"""
    id: str  # webhook event id
    type: PaymentMethodEventType
    customer_id: str
    payment_method_id: str

    def serialize(self, name, obj):
        if isinstance(obj, PaymentMethodEventType):
            obj = obj.value
        else:
            obj = super().serialize(name, obj)
        return obj

    def get_license(self) -> Optional[License]:
        pass

    def get_workspace(self) -> Optional[Workspace]:
        pass

    def get_billing_account(self) -> BillingAccount:
        return BillingAccount.objects.get(stripe_customer_id=self.customer_id)


@dataclass
class CustomerEvent(StripeEvent):
    """Contains stripe webhook information about customer actions"""
    id: str  # webhook event id
    type: CustomerEventType
    customer_id: str
    email: Optional[str]
    test_clock: Optional[str]
    livemode: bool
    description: Optional[str]

    def serialize(self, name, obj):
        if isinstance(obj, CustomerEventType):
            obj = obj.value
        else:
            obj = super().serialize(name, obj)
        return obj

    def get_license(self) -> Optional[License]:
        return None

    def get_workspace(self) -> Optional[Workspace]:
        return None
