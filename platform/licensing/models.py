import copy
import datetime
import re
import uuid
from enum import Enum
from typing import List, Literal, Optional, Union, Tuple
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.db import models
from django.db.models import Q
from django.db.models.manager import Manager

from platform_lib.data.common_models import MeterAttribute, SubscriptionStatus
from platform_lib.exceptions import LicenseNotExist, LicenseException
from platform_lib.utils import utcnow_with_tz


class Product(models.Model):
    class Meta:
        db_table = 'licensing_product'
        verbose_name_plural = 'Products'

    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
    name = models.CharField(max_length=128, null=False, blank=False, unique=True)
    config = models.JSONField(default=dict, null=False, blank=False)

    @staticmethod
    def __check_payment_mode(qa: bool):
        return settings.PAYMENT_MODE == 'test' or qa

    @property
    def mode(self) -> Literal['subscription']:
        return self.config['mode']

    @property
    def period(self) -> str:
        return self.config['period']

    @property
    def trial_period(self) -> Optional[str]:
        return self.config.get('trial_period')

    def get_product_plans(self, qa: bool = False) -> dict:
        """
        Returns plan info in format:
        {
            "name": "price_id"
        }
        Returns
        -------
        List[Dict]:
            List of dict with attribute name and attribute plans
        """
        return {
            name: (data['plans']['stripe_test'] if self.__check_payment_mode(qa)
                   else data['plans']['stripe_live'])
            for name, data in self.config['meter_attributes'].items()
        }

    @classmethod
    def get_product_by_stripe_id(cls, stripe_product_id: str, qa: bool = False) -> 'Product':
        if cls.__check_payment_mode(qa):
            getter = Q(config__stripe_test_product_id=stripe_product_id)
        else:
            getter = Q(config__stripe_live_product_id=stripe_product_id)

        return Product.objects.get(getter)

    @classmethod
    def get_product_by_name(cls, product_name: str) -> 'Product':
        return Product.objects.get(name=product_name)

    @classmethod
    def get_platform_config(cls) -> dict:
        return cls.objects.get(name='platform-cloud-basic').config

    def get_meter_attribute(self,
                            attr_name: str,
                            is_trial: bool = False,
                            qa: bool = False,
                            plan_name: Optional[str] = None) -> MeterAttribute:

        if plan_name is None:
            if self.__check_payment_mode(qa):
                plan_name = 'stripe_test'
            else:
                plan_name = 'stripe_live'

        attr = self.config['meter_attributes'][attr_name]

        return MeterAttribute(
            plan=attr['plans'][plan_name],
            limit=attr['trial_limit'] if is_trial else attr['limit'],
            title=attr_name,
            additional_properties={key: value for key, value in attr['additional_properties'].items()}
        )

    def get_meter_attributes(self, is_trial: bool = False, qa: bool = False) -> List[MeterAttribute]:
        if self.__check_payment_mode(qa):
            plan_name = 'stripe_test'
        else:
            plan_name = 'stripe_live'

        return [self.get_meter_attribute(
            attr_name=attr_name,
            is_trial=is_trial,
            plan_name=plan_name,
            qa=qa
        ) for attr_name in self.config['meter_attributes'].keys()]

    def period_in_days(self, is_trial: bool = False) -> int:
        period = self.config.get('trial_period') if is_trial else self.config.get('period')
        _, number, suffix = re.split(r'(\d+)', period)
        number = int(number)
        now = utcnow_with_tz()
        if suffix == 'd':
            return number
        elif suffix == 'm':
            return (now + relativedelta(months=number) - now).days
        elif suffix == 'y':
            return (now + relativedelta(years=number) - now).days

        raise NotImplementedError(f'Incorrect period {period} in product {self.name}')

    def flow_operation(self, to: str) -> Optional[Literal['upgrade', 'downgrade']]:
        return next(filter(lambda value: to in value[1], self.config['flow'].items()), [None])[0]


class BillingAccount(models.Model):
    class Meta:
        db_table = 'licensing_billing_account'
        verbose_name_plural = 'BillingAccounts'

    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='billing_account')
    stripe_customer_id = models.CharField(max_length=255)  # to not duplicate stripe customers
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def username(self) -> str:
        return self.user.username

    @property
    def is_qa(self) -> bool:
        return self.user.groups.filter(name__iexact=settings.QA_GROUP).exists()

    @property
    def groups(self) -> Manager[Group]:
        return self.user.groups

    @classmethod
    def get_by_username(cls, username: str) -> 'BillingAccount':
        return cls.objects.get(user__username=username)

    @classmethod
    def lock_account(cls, client: 'BillingAccount') -> 'BillingAccount':
        return cls.objects.select_for_update().get(id=client.id)

    @classmethod
    def get_or_create(cls, username: str, customer_id: Optional[str] = None) -> Tuple['BillingAccount', bool]:
        user = User.objects.get(username=username)

        params = {'user': user}
        if customer_id:
            params.update({'stripe_customer_id': customer_id})  # type: ignore

        return cls.objects.get_or_create(**params)  # type: ignore


class License(models.Model):
    class Meta:
        db_table = 'licensing_license'
        verbose_name_plural = 'Licenses'

    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
    billing_account = models.ForeignKey(BillingAccount,
                                        on_delete=models.CASCADE,
                                        null=False,
                                        blank=False,
                                        related_name='licenses')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='licenses')
    workspace = models.OneToOneField('user_domain.Workspace', on_delete=models.CASCADE, null=True, blank=True)
    config = models.JSONField(default=dict, null=False, blank=False)
    expiration_date = models.DateTimeField()
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    @classmethod
    def _create(cls,
                billing_account: BillingAccount,
                product: Product,
                subscription_id: str,
                expiration_date: datetime.datetime,
                stripe_item_ids: dict,
                is_trial: bool = False,
                workspace_id: Optional[str] = None,
                lic_id: Optional[uuid.UUID] = None):

        from user_domain.managers import WorkspaceManager  # TODO: remove after creating microservice

        workspace = WorkspaceManager.get_workspace(workspace_id) if workspace_id else None

        config = {
            'meter_attributes': {},
            'subscription': subscription_id,
            'status': SubscriptionStatus.TRIALING.value if is_trial else SubscriptionStatus.ACTIVE.value,
            'next_payment_attempt': None,
            'cancel_at_period_end': is_trial,
        }

        product_attrs = product.get_meter_attributes(is_trial=is_trial, qa=billing_account.is_qa)

        for product_attr in product_attrs:
            product_attr.stripe_item_id = stripe_item_ids.get(product_attr.title, '')
            # zero additional property
            if product_attr.additional_properties is not None:
                product_attr.additional_properties = {
                    key: None for key, value in product_attr.additional_properties.items()
                }
            config['meter_attributes'][product_attr.title] = product_attr.to_dict()

        attributes = {
            'billing_account': billing_account,
            'product': product,
            'config': config,
            'expiration_date': expiration_date
        }

        if workspace is not None:
            attributes['workspace'] = workspace

        if lic_id is not None:
            attributes['id'] = lic_id

        return cls.objects.create(**attributes)

    @property
    def period_in_days(self) -> int:
        if self.product is None:
            raise LicenseException('Internal error: license has not product')

        product_config = self.product.config
        period = product_config.get('trial_period') if self.is_trial else product_config.get('period')
        _, number, suffix = re.split(r'(\d+)', period)
        number = int(number)

        expiration_date = self.expiration_date

        if suffix == 'd':
            return number
        elif suffix == 'm':
            return (expiration_date - (expiration_date - relativedelta(months=number))).days  # noqa
        elif suffix == 'y':
            return (expiration_date - (expiration_date - relativedelta(years=number))).days  # noqa

        raise LicenseException(f'Incorrect period {period} in product {self.product.name}')

    @classmethod
    def lock_license(cls, lic: 'License') -> 'License':
        return cls.objects.select_for_update().get(id=lic.id)

    def get_meter_attribute(self, name: str) -> MeterAttribute:
        return MeterAttribute.from_dict(self.config['meter_attributes'][name])  # type: ignore

    def set_meter_attribute(self, name: str, value: MeterAttribute):
        self.config['meter_attributes'][name] = value.to_dict()

    @property
    def channels(self) -> MeterAttribute:
        return self.get_meter_attribute('channels')

    @channels.setter
    def channels(self, value: MeterAttribute):
        self.set_meter_attribute('channels', value)

    @property
    def persons_in_base(self) -> MeterAttribute:
        return self.get_meter_attribute('persons_in_base')

    @persons_in_base.setter
    def persons_in_base(self, value: MeterAttribute):
        self.set_meter_attribute('persons_in_base', value)

    @property
    def transactions(self) -> MeterAttribute:
        return self.get_meter_attribute('transactions')

    @transactions.setter
    def transactions(self, value: MeterAttribute):
        self.set_meter_attribute('transactions', value)

    @property
    def subscription_id(self) -> str:
        return self.config.get('subscription', '')

    @subscription_id.setter
    def subscription_id(self, value: str):
        self.config['subscription'] = value

    @property
    def status(self) -> str:
        return self.config.get('status', '')

    @status.setter
    def status(self, value: str):
        self.config['status'] = SubscriptionStatus(value).value

    @property
    def is_trial(self) -> bool:
        return self.status == SubscriptionStatus.TRIALING.value

    @property
    def next_payment_attempt(self) -> Optional[str]:
        return self.config.get('next_payment_attempt')

    @next_payment_attempt.setter
    def next_payment_attempt(self, value: Optional[str]):
        self.config['next_payment_attempt'] = value

    @property
    def meter_attributes(self) -> List[MeterAttribute]:
        return [getattr(self, name) for name in self.config['meter_attributes'].keys()]

    @property
    def cancel_at_period_end(self) -> bool:
        return self.config.get('cancel_at_period_end')

    @cancel_at_period_end.setter
    def cancel_at_period_end(self, value: bool):
        self.config['cancel_at_period_end'] = value


class AutonomousLicense(License):
    class Meta:
        proxy = True

    @classmethod
    def create(cls,
               billing_account: BillingAccount,
               product: Product,
               subscription_id: str,
               expiration_date: datetime.datetime,
               stripe_item_ids: dict,
               is_trial: bool,
               lic_id: Optional[Union[str, uuid.UUID]] = None) -> 'AutonomousLicense':
        attrs = copy.copy(locals())
        del attrs['cls']
        return cls._create(**attrs)


class WorkspaceLicense(License):
    class Meta:
        proxy = True

    @classmethod
    def create(cls,
               billing_account: BillingAccount,
               product: Product,
               subscription_id: str,
               expiration_date: datetime.datetime,
               stripe_item_ids: dict,
               workspace_id: str,
               is_trial: bool,
               lic_id: Optional[Union[str, uuid.UUID]] = None) -> 'WorkspaceLicense':

        attrs = copy.copy(locals())
        del attrs['cls']
        return cls._create(**attrs)

    @classmethod
    def get_by_workspace(cls, workspace_id: Union[str, uuid.UUID]) -> 'WorkspaceLicense':
        try:
            return cls.objects.get(workspace_id=workspace_id)
        except License.DoesNotExist:
            raise LicenseNotExist


class WebhookLog(models.Model):
    class Meta:
        db_table = 'licensing_webhook_log'
        verbose_name_plural = 'WebhookLogs'
        constraints = [
            models.UniqueConstraint(fields=['source', 'request_id'], name='unique_request_per_source')
        ]

    class Source(Enum):
        stripe = 'stripe'

    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)
    source = models.CharField(max_length=64)
    request_id = models.CharField(max_length=255)
    payload = models.JSONField(blank=True, default=dict)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    @classmethod
    def from_stripe(cls, request_id: str, payload: dict) -> 'WebhookLog':
        return cls.objects.create(
            source=cls.Source.stripe.value,
            request_id=request_id,
            payload=payload
        )

    @classmethod
    def is_exist(cls, request_id: str) -> bool:
        return cls.objects.filter(request_id=request_id).exists()
