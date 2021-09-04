import copy
import datetime
import logging
import math
import uuid
from enum import Enum
from typing import List, Optional, Any, Tuple, Union

from django.db.models import Q, QuerySet
from django.db.transaction import atomic

from licensing.models import Product, BillingAccount, License, AutonomousLicense, WorkspaceLicense
from licensing.payment.models import Subscription
from licensing.payment.stripe.api import StripeAPI
from platform_lib.data.common_models import MeterAttribute, SubscriptionStatus
from platform_lib.exceptions import LicenseAttributeNotExist, LicenseLimitAttribute, \
    ProductAttributeNotExist
from platform_lib.utils import utcnow_with_tz

logger = logging.getLogger(__name__)


class MeterAttributeManager:
    class Title(str, Enum):
        CHANNELS = 'channels'
        PERSONS_IN_BASE = 'persons_in_base'
        TRANSACTIONS = 'transactions'

    @classmethod
    def __channels_report_info(cls,
                               lic: Union[License, AutonomousLicense],
                               attribute: MeterAttribute) -> Tuple[str, int]:
        return attribute.stripe_item_id, attribute.gross_uses

    @classmethod
    def __transactions_report_info(cls,
                                   lic: Union[License, AutonomousLicense],
                                   attribute: MeterAttribute) -> Tuple[str, int]:
        return attribute.stripe_item_id, attribute.gross_uses

    @classmethod
    def __person_in_base_report_info(cls,
                                     lic: Union[License, AutonomousLicense],
                                     attribute: MeterAttribute) -> Tuple[str, int]:
        free_usage, usage_edge = BaseLicenseManager.get_additional_property(lic,
                                                                            cls.Title(attribute.title),
                                                                            ['free_usage', 'usage_edge'])

        current_exceed_stage = math.ceil((attribute.gross_uses - free_usage) / usage_edge)

        return attribute.stripe_item_id, current_exceed_stage

    @classmethod
    def get_report_mapping(cls):
        return {
            cls.Title.CHANNELS: cls.__channels_report_info,
            cls.Title.PERSONS_IN_BASE: cls.__person_in_base_report_info,
            cls.Title.TRANSACTIONS: cls.__transactions_report_info
        }

    @classmethod
    def prepare_meter_info_for_report(cls,
                                      lic: Union[License, AutonomousLicense],
                                      attribute: MeterAttribute) -> Tuple[str, int]:
        return cls.get_report_mapping()[cls.Title(attribute.title)](lic, attribute)  # noqa


class LicenseManagerMixin:
    lic_object = License  # type: Any

    @classmethod
    def get_all_active_licenses(cls) -> QuerySet[lic_object]:
        filter_ = Q(workspace__config__is_active=True) | Q(workspace__isnull=True)
        exclude_ = Q(config__status__in=[SubscriptionStatus.CANCELED.value, SubscriptionStatus.UNPAID.value])

        return cls.lic_object.objects.filter(filter_).exclude(exclude_)

    @classmethod
    def get_all_licenses(cls):
        return cls.lic_object.objects.all()

    @classmethod
    @atomic
    def update_next_payment_attempt(cls, lic: lic_object, payment_attempt: Optional[datetime.datetime]) -> lic_object:
        new_date = payment_attempt.isoformat() if payment_attempt else None
        lock_lic = cls.lic_object.lock_license(lic)
        lock_lic.next_payment_attempt = new_date
        lock_lic.save()

        return lock_lic

    @classmethod
    def get_meter_attribute_in_stripe_format(cls, lic: lic_object, name: str) -> Optional[dict]:
        meter_attribute = getattr(lic, name, None)

        return {
            'id': meter_attribute.stripe_item_id,
            'price': meter_attribute.plan,
        } if meter_attribute is not None else None

    @classmethod
    def get_additional_property(cls,
                                lic: lic_object,
                                meter_attribute_title: MeterAttributeManager.Title,
                                property_titles: List[str]) -> List[Any]:

        title = meter_attribute_title.value
        result_list = []

        @cls._check_attribute(lic, title)
        def __inner(current_attribute, current_prod_attr, *args, **kwargs):
            for property_title in property_titles:
                property_value = current_attribute.additional_properties.get(property_title)
                if property_value is None:
                    property_value = current_prod_attr.additional_properties.get(property_title)
                result_list.append(property_value)

        __inner()
        return result_list

    @classmethod
    def _zero_metered_attributes(cls, lic: lic_object) -> lic_object:
        loc_lic = License.lock_license(lic)

        for meter_attribute in loc_lic.meter_attributes:
            meter_attribute.uses = 0
            meter_attribute.gross_uses = 0
            meter_attribute.allowed = meter_attribute.limit

            loc_lic.set_meter_attribute(meter_attribute.title, meter_attribute)

        loc_lic.save()

        return loc_lic

    @classmethod
    def _create(cls,
                product: Product,
                is_trial: bool,
                username: str,
                workspace_id: Optional[str] = None) -> lic_object:

        billing_account = BillingAccount.objects.get(user__username=username)
        qa = billing_account.is_qa

        stripe_api = StripeAPI(billing_account)

        items = [{
            'price': attribute.plan,
            'metadata': {'active': 'true'}
        } for attribute in product.get_meter_attributes(is_trial, qa=qa)]

        license_id = uuid.uuid4()

        # stores in stripe subscription
        metadata = {'workspace': workspace_id} if workspace_id else {'license': license_id}  # type: ignore

        attrs = {
            'customer_id': billing_account.stripe_customer_id,
            'items': items,
            'metadata': metadata
        }

        if is_trial:
            attrs['trial_period_days'] = str(product.period_in_days(is_trial=True))

        subscription_raw = stripe_api.create_subscription(**attrs)  # type: ignore
        subscription = Subscription.from_dict(subscription_raw)

        item_ids = {item.title: item.stripe_item_id for item in subscription.meter_attributes or []}

        attributes = {
            'billing_account': billing_account,
            'product': product,
            'subscription_id': subscription.id,
            'expiration_date': subscription.expiration_date,
            'stripe_item_ids': item_ids,
            'lic_id': license_id
        }

        if workspace_id is not None:
            attributes['workspace_id'] = workspace_id

        if is_trial is not None:
            attributes['is_trial'] = is_trial

        lic = cls.lic_object.create(**attributes)

        return lic

    @staticmethod
    def _delete(lic: lic_object) -> bool:
        deleted, _ = lic.delete()
        return bool(deleted)

    @classmethod
    def _update_license(cls,
                        lic: lic_object,
                        subscription_id: Optional[str] = None,
                        cancel_at_period_end: bool = False,
                        expiration_date: Optional[datetime.datetime] = None,
                        status: Optional[SubscriptionStatus] = None,
                        metered_attributes: Optional[List[MeterAttribute]] = None,
                        product: Optional[Product] = None) -> lic_object:

        lock_lic = cls.lic_object.lock_license(lic)
        lock_lic.cancel_at_period_end = cancel_at_period_end

        if expiration_date is not None:
            lock_lic.expiration_date = expiration_date
        if status is not None:
            lock_lic.status = status.value
        if subscription_id is not None:
            lock_lic.subscription_id = subscription_id
        if product is not None:
            lock_lic.product = product
        if metered_attributes is not None:
            for meter_attribute in metered_attributes:
                @cls._check_attribute(lic, meter_attribute.title)
                def __inner(lock_lic, new_attribute, current_attribute, *args, **kwargs):
                    if new_attribute.limit is not None:
                        if new_attribute.limit == -1:
                            current_attribute.allowed = current_attribute.limit = -1
                        else:
                            # do not allow decrease limit manual
                            new_limit = max(new_attribute.limit, current_attribute.limit)

                            current_attribute.allowed = new_limit - current_attribute.uses
                            current_attribute.limit = new_limit

                    if new_attribute.plan:
                        current_attribute.plan = new_attribute.plan
                    if new_attribute.stripe_item_id:
                        current_attribute.stripe_item_id = new_attribute.stripe_item_id

                    setattr(lock_lic, new_attribute.title, current_attribute)

                __inner(lock_lic, meter_attribute)

        lock_lic.save()

        return lock_lic

    @classmethod
    @atomic
    def _check_meter_attribute(cls, lic: lic_object, title: str, increment: int = 1) -> bool:
        lock_lic = cls.lic_object.lock_license(lic)

        @cls._check_attribute(lock_lic, title)
        def __inner(current_attribute, *args, **kwargs):

            if current_attribute.limit != -1:
                if current_attribute.uses + increment > current_attribute.limit:
                    return False

            return True

        return __inner()

    @classmethod
    @atomic
    def _increment_meter_attribute(cls, lic: lic_object, title: str, increment: int = 1) -> lic_object:
        lock_lic = cls.lic_object.lock_license(lic)

        @cls._check_attribute(lock_lic, title)
        def __inner(current_attribute, *args, **kwargs):
            current_attribute.uses += increment
            if current_attribute.uses > current_attribute.gross_uses:
                current_attribute.gross_uses += increment

            if current_attribute.limit != -1:
                if current_attribute.uses > current_attribute.limit:
                    raise LicenseLimitAttribute(title)
                current_attribute.allowed -= increment

            return current_attribute

        attribute = __inner()

        setattr(lock_lic, title, attribute)
        lock_lic.save()

        return lock_lic

    @classmethod
    def _decrement_meter_attribute(cls, lic: lic_object, title: str, decrement: int = 1) -> lic_object:
        lock_lic = cls.lic_object.lock_license(lic)

        @cls._check_attribute(lock_lic, title)
        def __inner(current_attribute, *args, **kwargs):
            current_attribute.uses -= decrement
            if current_attribute.limit != -1:
                current_attribute.allowed += decrement

            return current_attribute

        attribute = __inner()
        setattr(lock_lic, title, attribute)
        lock_lic.save()

        return lock_lic

    @staticmethod
    def _is_valid(lic: lic_object) -> bool:
        return utcnow_with_tz() < lic.expiration_date

    @staticmethod
    def _check_attribute(lic: lic_object, title: str):
        def decorator(func):
            def wrapper(*args, **kwargs, ):
                try:
                    attribute = getattr(lic, title)
                except AttributeError:
                    raise LicenseAttributeNotExist(title)
                try:
                    prod_attribute = lic.product.get_meter_attribute(
                        attr_name=title,
                        is_trial=lic.is_trial,
                        qa=lic.billing_account.is_qa
                    )
                except KeyError:
                    raise ProductAttributeNotExist(title)

                return func(*args, **kwargs, current_attribute=attribute, current_prod_attr=prod_attribute)

            return wrapper

        return decorator

    @staticmethod
    def _prepare_locals(locals: dict,
                        new_info: Optional[List[Tuple[str, Any]]] = None,
                        exclude_attrs: Optional[List[str]] = None):
        if exclude_attrs is None:
            exclude_attrs = ['cls', 'license_id', 'workspace_id']
        attrs = copy.copy(locals)

        for info in new_info or []:
            attrs[info[0]] = info[1]

        for exclude_attr in exclude_attrs:
            if exclude_attr in attrs:
                del attrs[exclude_attr]

        return attrs

    @classmethod
    def _obtain_license(cls, id: Union[str, uuid.UUID]) -> lic_object:
        return cls.lic_object.get(id=id)

    @classmethod
    def _route_method(cls,
                      method_name: str,
                      method_locals: dict,
                      id: Optional[Union[str, uuid.UUID]] = None,
                      exclude_attrs: Optional[List[str]] = None) -> Any:
        if id is not None:
            new_info = [('lic', cls._obtain_license(id))]
        else:
            new_info = None

        attrs = cls._prepare_locals(method_locals, new_info, exclude_attrs)
        return getattr(cls, f"_{method_name}")(**attrs)


class BaseLicenseManager(LicenseManagerMixin):
    lic_object = LicenseManagerMixin.lic_object  # type: Any

    @classmethod
    def delete(cls, lic: lic_object) -> bool:
        return cls._route_method("delete", locals())

    @classmethod
    @atomic
    def update_license(cls,
                       lic: lic_object,
                       cancel_at_period_end: bool = False,
                       subscription_id: Optional[str] = None,
                       expiration_date: Optional[datetime.datetime] = None,
                       status: Optional[SubscriptionStatus] = None,
                       metered_attributes: Optional[List[MeterAttribute]] = None,
                       product: Optional[Product] = None) -> lic_object:
        return cls._route_method("update_license", locals())

    @classmethod
    @atomic
    def check_meter_attribute(cls, lic: lic_object, title: str, increment: int = 1) -> bool:
        return cls._route_method("check_meter_attribute", locals())

    @classmethod
    @atomic
    def increment_meter_attribute(cls, lic: lic_object, title: str, increment: int = 1) -> lic_object:
        return cls._route_method("increment_meter_attribute", locals())

    @classmethod
    @atomic
    def decrement_meter_attribute(cls, lic: lic_object, title: str, decrement: int = 1) -> lic_object:
        return cls._route_method("decrement_meter_attribute", locals())

    @classmethod
    def is_valid(cls, lic: lic_object) -> bool:
        return cls._route_method("is_valid", locals())

    @classmethod
    def zero_metered_attributes(cls, lic: lic_object) -> lic_object:
        return cls._route_method("zero_metered_attributes", locals())


class AutonomousLicenseManager(LicenseManagerMixin):
    class ProductName(str, Enum):
        IMAGE_API_BASE = 'image-api-base'
        IMAGE_API_STARTUP = 'image-api-startup'
        IMAGE_API_EXPERT = 'image-api-expert'
        IMAGE_API_ADVANCE = 'image-api-advanced'

    lic_object = AutonomousLicense  # type: Any

    @classmethod
    def get_all_active_licenses(cls) -> QuerySet[lic_object]:
        return cls.lic_object.objects.filter(workspace__isnull=True).exclude(
                                              config__status__in=[SubscriptionStatus.CANCELED.value,
                                                                  SubscriptionStatus.UNPAID.value])

    @classmethod
    def get_all_licenses(cls):
        return cls.lic_object.objects.filter(workspace__isnull=True)

    @classmethod
    def create(cls, is_trial: bool, product_name: ProductName, username: str) -> lic_object:
        # var for locals() and then for _create method in BaseLicenseManager
        product = Product.get_product_by_name(product_name.value)

        return cls._route_method("create", locals(), exclude_attrs=['cls', 'product_name'])

    @classmethod
    def delete(cls, license_id: Union[str, uuid.UUID]) -> bool:
        return cls._route_method("delete", locals(), id=license_id)

    @classmethod
    @atomic
    def update_license(cls,
                       license_id: Union[str, uuid.UUID],
                       cancel_at_period_end: bool = False,
                       subscription_id: Optional[str] = None,
                       expiration_date: Optional[datetime.datetime] = None,
                       status: Optional[SubscriptionStatus] = None,
                       metered_attributes: Optional[List[MeterAttribute]] = None,
                       product: Optional[Product] = None) -> lic_object:
        return cls._route_method("update_license", locals(), id=license_id)

    @classmethod
    @atomic
    def check_meter_attribute(cls, license_id: Union[str, uuid.UUID], title: str, increment: int = 1) -> bool:
        return cls._route_method("check_meter_attribute", locals(), id=license_id)

    @classmethod
    @atomic
    def increment_meter_attribute(cls, license_id: Union[str, uuid.UUID], title: str, increment: int = 1) -> lic_object:
        return cls._route_method("increment_meter_attribute", locals(), id=license_id)

    @classmethod
    @atomic
    def decrement_meter_attribute(cls, license_id: Union[str, uuid.UUID], title: str, decrement: int = 1) -> lic_object:
        return cls._route_method("decrement_meter_attribute", locals(), id=license_id)

    @classmethod
    def is_valid(cls, license_id: Union[str, uuid.UUID]) -> bool:
        return cls._route_method("is_valid", locals(), id=license_id)

    @classmethod
    def zero_metered_attributes(cls, license_id: Union[str, uuid.UUID]) -> lic_object:
        return cls._route_method("zero_metered_attributes", locals(), id=license_id)

    @classmethod
    def _obtain_license(cls, id: Union[str, uuid.UUID]) -> lic_object:
        return cls.lic_object.objects.get(id=id)


class WorkspaceLicenseManager(LicenseManagerMixin):
    lic_object = WorkspaceLicense  # type: Any

    @classmethod
    def get_all_active_licenses(cls) -> QuerySet[lic_object]:
        return cls.lic_object.objects.filter(workspace__config__is_active=True).exclude(
                                              config__status__in=[SubscriptionStatus.CANCELED.value,
                                                                  SubscriptionStatus.UNPAID.value])

    @classmethod
    def get_all_licenses(cls):
        return cls.lic_object.objects.exclude(workspace__isnull=True)

    @classmethod
    def create(cls,
               username: str,
               workspace_id: Union[str, uuid.UUID]) -> lic_object:
        # var for locals() and then for _create method in BaseLicenseManager
        product = Product.get_product_by_name('platform-cloud-basic')
        is_trial = True

        return cls._route_method("create", locals(), exclude_attrs=['cls'])

    @classmethod
    def delete(cls, workspace_id: Union[str, uuid.UUID]) -> bool:
        return cls._route_method("delete", locals(), id=workspace_id)

    @classmethod
    @atomic
    def update_license(cls,
                       workspace_id: Union[str, uuid.UUID],
                       cancel_at_period_end: bool = False,
                       subscription_id: Optional[str] = None,
                       expiration_date: Optional[datetime.datetime] = None,
                       status: Optional[SubscriptionStatus] = None,
                       metered_attributes: Optional[List[MeterAttribute]] = None,
                       product: Optional[Product] = None) -> lic_object:
        return cls._route_method("update_license", locals(), id=workspace_id)

    @classmethod
    @atomic
    def check_meter_attribute(cls,
                              workspace_id: Union[str, uuid.UUID],
                              title: str,
                              increment: int = 1) -> bool:
        return cls._route_method("check_meter_attribute", locals(), id=workspace_id)

    @classmethod
    @atomic
    def increment_meter_attribute(cls,
                                  workspace_id: Union[str, uuid.UUID],
                                  title: str,
                                  increment: int = 1) -> lic_object:
        return cls._route_method("increment_meter_attribute", locals(), id=workspace_id)

    @classmethod
    @atomic
    def decrement_meter_attribute(cls,
                                  workspace_id: Union[str, uuid.UUID],
                                  title: str,
                                  decrement: int = 1) -> lic_object:
        return cls._route_method("decrement_meter_attribute", locals(), id=workspace_id)

    @classmethod
    def is_valid(cls, workspace_id: Union[str, uuid.UUID]) -> bool:
        return cls._route_method("is_valid", locals(), id=workspace_id)

    @classmethod
    def zero_metered_attributes(cls, workspace_id: Union[str, uuid.UUID]) -> lic_object:
        return cls._route_method("zero_metered_attributes", locals(), id=workspace_id)

    @classmethod
    def _obtain_license(cls, id: Union[str, uuid.UUID]) -> lic_object:
        return cls.lic_object.get_by_workspace(id)
