from datetime import timedelta
from typing import List
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.test import TestCase, tag
from freezegun import freeze_time

from licensing.configs import products
from licensing.managers import WorkspaceLicenseManager, BaseLicenseManager, AutonomousLicenseManager
from licensing.models import Product, BillingAccount
from platform_lib.data.common_models import SubscriptionStatus, MeterAttribute
from platform_lib.exceptions import LicenseAttributeNotExist, LicenseLimitAttribute, LicenseNotExist
from platform_lib.utils import utcnow_with_tz
from user_domain.managers import WorkspaceManager


@freeze_time(utcnow_with_tz())
@tag('cloud')
class WorkspaceLicenseManagerTest:
    product: Product

    stripe_trial_subscription_patch = {
        'current_period_end': int((utcnow_with_tz() + timedelta(days=14)).timestamp()),
        'cancel_at_period_end': True,
        'status': 'trialing',
        'items': {
            'data': [
                {
                    'price': {
                        'id': 'price_id',
                        'product': 'product_id',
                        'unit_amount': 2000,
                        'metadata': {
                            'title': 'channels'
                        }
                    },
                    'id': 'some_id',
                    'quantity': 1,
                    'metadata': {
                        'active': 'true'
                    }
                }
            ]
        }
    }

    @staticmethod
    @patch('licensing.payment.stripe.api.StripeAPI.get_or_create_customer', return_value='some_id')
    @patch('licensing.payment.stripe.api.StripeAPI.create_subscription',
           return_value={'id': 'subs_id', 'trial_end': (utcnow_with_tz() + timedelta(days=14)).timestamp(),
                         **stripe_trial_subscription_patch})
    def _register_account(username: str, __get_or_create_customer, __create_subscription):
        user = User.objects.create_user(username=username, email=username, password='zaq11qaz')
        BillingAccount.get_or_create(username=username)
        workspace = WorkspaceManager.create_workspace(f"Workspace {username}", username=username)
        WorkspaceLicenseManager.create(username, str(workspace.id))

        return user, workspace

    def _upgrade_license(self, lic: WorkspaceLicenseManager.lic_object) -> WorkspaceLicenseManager.lic_object:
        return WorkspaceLicenseManager.update_license(
            workspace_id=lic.workspace_id,
            expiration_date=lic.expiration_date + timedelta(days=self.product.period_in_days()),
            status=SubscriptionStatus.ACTIVE,
            metered_attributes=self.product.get_meter_attributes(),
            product=self.product
        )

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            name=cls.product,
            config=products[cls.product]
        )
        cls.meter_attributes = list(cls.product.config['meter_attributes'].keys())
        cls.email = 'test@mail.com'
        cls.user, cls.workspace = cls._register_account(cls.email)

    def test_create_trial_license(self):
        cloud_config = self.product.config
        lic = WorkspaceLicenseManager.lic_object.get_by_workspace(self.workspace.id)

        time_with_period = utcnow_with_tz() + timedelta(days=self.product.period_in_days(is_trial=True))
        self.assertAlmostEqual(lic.expiration_date, time_with_period, delta=timedelta(seconds=10))
        self.assertEqual(lic.product.name, self.product.name)
        self.assertTrue(lic.is_trial)

        for attr in lic.meter_attributes:
            attr_limit = cloud_config['meter_attributes'][attr.title]['trial_limit']
            additional_properties = cloud_config['meter_attributes'][attr.title]['additional_properties']
            additional_properties = {key: None for key in additional_properties.keys()}
            self.assertEqual(attr.limit, attr_limit)
            self.assertEqual(attr.allowed, attr_limit)
            self.assertEqual(attr.uses, 0)
            self.assertEqual(attr.gross_uses, 0)
            self.assertEqual(attr.additional_properties, additional_properties)

    def test_upgrade_license(self):
        cloud_config = self.product.config
        lic = self._upgrade_license(WorkspaceLicenseManager.lic_object.get_by_workspace(self.workspace.id))

        self.assertFalse(lic.is_trial)

        for attr in lic.meter_attributes:
            attr_limit = cloud_config['meter_attributes'][attr.title]['limit']
            additional_properties = cloud_config['meter_attributes'][attr.title]['additional_properties']
            additional_properties = {key: None for key in additional_properties.keys()}
            self.assertEqual(attr.limit, attr_limit)
            self.assertEqual(attr.allowed, attr_limit)
            self.assertEqual(attr.uses, 0)
            self.assertEqual(attr.gross_uses, 0)
            self.assertEqual(attr.additional_properties, additional_properties)

    def test_check_meter_attribute(self):
        for attr in self.meter_attributes:
            self.assertTrue(WorkspaceLicenseManager.check_meter_attribute(self.workspace.id, attr))

        WorkspaceLicenseManager.increment_meter_attribute(
            workspace_id=self.workspace.id,
            title='channels',
            increment=self.product.config['meter_attributes']['channels']['trial_limit'])
        self.assertFalse(WorkspaceLicenseManager.check_meter_attribute(self.workspace.id, 'channels'))

    def test_increment_trial_license_attribute_not_exist(self):
        with self.assertRaises(LicenseAttributeNotExist) as ex:
            WorkspaceLicenseManager.increment_meter_attribute(self.workspace.id, 'not_exist')

        self.assertEqual(ex.exception.__str__(), 'License meter-attribute "not_exist" does not exist')

    def test_increment_trial_license_limit_attribute(self):
        def increment_test(lic, attr: str):
            for _ in range(getattr(lic, attr).limit+1):
                WorkspaceLicenseManager.increment_meter_attribute(lic.workspace.id, attr)

        lic = WorkspaceLicenseManager.lic_object.get_by_workspace(self.workspace.id)
        for attr in lic.meter_attributes:
            with self.assertRaises(LicenseLimitAttribute) as ex:
                increment_test(lic, attr.title)

            self.assertEqual(ex.exception.__str__(), f'License attribute "{attr.title}" limit exceeded')

    def test_increment_meter_attributes(self):
        workspace_id = self.workspace.id

        with self.subTest(msg='Increment in trial'):
            source_lic = WorkspaceLicenseManager.lic_object.get_by_workspace(workspace_id)
            for source_attr in source_lic.meter_attributes:
                modified_lic = WorkspaceLicenseManager.increment_meter_attribute(workspace_id, source_attr.title)

                modified_attr = getattr(modified_lic, source_attr.title)

                self.assertEqual(modified_attr.uses, source_attr.uses + 1)
                self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses + 1)
                self.assertEqual(modified_attr.allowed, source_attr.allowed - 1)

        with self.subTest(msg='Increment in cloud'):
            source_lic = self._upgrade_license(WorkspaceLicenseManager.lic_object.get_by_workspace(workspace_id))
            for source_attr in source_lic.meter_attributes:
                modified_lic = WorkspaceLicenseManager.increment_meter_attribute(workspace_id, source_attr.title)

                modified_attr = getattr(modified_lic, source_attr.title)

                self.assertEqual(modified_attr.uses, source_attr.uses + 1)
                self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses + 1)
                self.assertEqual(modified_attr.allowed, source_attr.allowed)

    def test_decrement_license_attribute_not_exist(self):
        with self.assertRaises(LicenseAttributeNotExist) as ex:
            WorkspaceLicenseManager.decrement_meter_attribute(self.workspace.id, 'some_license')

        self.assertEqual(ex.exception.__str__(), 'License meter-attribute "some_license" does not exist')

    def test_decrement_meter_attributes(self):
        workspace_id = self.workspace.id
        for attr in self.meter_attributes:
            WorkspaceLicenseManager.increment_meter_attribute(workspace_id, attr, 3)

        with self.subTest(msg='Decrement in trial'):
            source_lic = WorkspaceLicenseManager.lic_object.get_by_workspace(workspace_id)
            for source_attr in source_lic.meter_attributes:
                modified_lic = WorkspaceLicenseManager.decrement_meter_attribute(workspace_id, source_attr.title)

                modified_attr = getattr(modified_lic, source_attr.title)

                self.assertEqual(modified_attr.uses, source_attr.uses - 1)
                self.assertEqual(modified_attr.allowed, source_attr.allowed + 1)
                self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses)

        with self.subTest(msg='Decrement in cloud'):
            source_lic = self._upgrade_license(WorkspaceLicenseManager.lic_object.get_by_workspace(workspace_id))
            for source_attr in source_lic.meter_attributes:
                modified_lic = WorkspaceLicenseManager.decrement_meter_attribute(workspace_id, source_attr.title)

                modified_attr = getattr(modified_lic, source_attr.title)

                self.assertEqual(modified_attr.uses, source_attr.uses - 1)
                self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses)

    def test_is_valid_true(self):
        result = WorkspaceLicenseManager.is_valid(self.workspace.id)
        self.assertTrue(result)

    def test_is_valid_false(self):
        workspace_id = self.workspace.id
        lic = WorkspaceLicenseManager.lic_object.get_by_workspace(workspace_id)
        lic.expiration_date = utcnow_with_tz() - timedelta(minutes=1)
        lic.save()
        result = WorkspaceLicenseManager.is_valid(workspace_id)
        self.assertFalse(result)

    def test_get_all_active_licenses(self):
        user, workspace = self._register_account('inactive@mail.com')

        with self.subTest('All active'):
            active_licenses = WorkspaceLicenseManager.get_all_active_licenses()
            source_licenses = {WorkspaceLicenseManager.lic_object.get_by_workspace(str(ws.id)).id
                               for ws in [self.workspace, workspace]}
            self.assertEqual(source_licenses, {lic.id for lic in active_licenses})

        with self.subTest('One inactive'):
            WorkspaceManager.deactivate_workspace(workspace)
            active_licenses = WorkspaceLicenseManager.get_all_active_licenses()
            source_licenses = {WorkspaceLicenseManager.lic_object.get_by_workspace(str(ws.id)).id
                               for ws in [self.workspace]}
            self.assertEqual(source_licenses, {lic.id for lic in active_licenses})

    def test_delete_license(self):
        WorkspaceLicenseManager.delete(self.workspace.id)

        with self.assertRaises(LicenseNotExist):
            WorkspaceLicenseManager.lic_object.get_by_workspace(self.workspace.id)

    def test_reset_meter_attributes(self):
        lic = WorkspaceLicenseManager.zero_metered_attributes(self.workspace.id)

        for attr in lic.meter_attributes:
            WorkspaceLicenseManager.increment_meter_attribute(self.workspace.id, attr.title)

        for attr in lic.meter_attributes:
            self.assertEqual(attr.uses, 0)
            self.assertEqual(attr.gross_uses, 0)
            self.assertEqual(attr.allowed, attr.limit)

    def test_update_license(self):
        lic = WorkspaceLicenseManager.lic_object.get_by_workspace(self.workspace.id)
        lic.persons_in_base = MeterAttribute(limit=500, title='persons_in_base')
        new_expiration_date = lic.expiration_date + timedelta(self.product.period_in_days())
        new_subscription_id = 'new_subscription_id'
        modified_lic = WorkspaceLicenseManager.update_license(
            workspace_id=self.workspace.id,
            cancel_at_period_end=True,
            subscription_id=new_subscription_id,
            expiration_date=new_expiration_date,
            metered_attributes=lic.meter_attributes,
            status=SubscriptionStatus.PAST_DUE
        )

        self.assertTrue(modified_lic.cancel_at_period_end)
        self.assertEqual(modified_lic.subscription_id, 'new_subscription_id')
        self.assertEqual(modified_lic.expiration_date, new_expiration_date)
        self.assertEqual(modified_lic.persons_in_base.limit, 500)
        self.assertEqual(modified_lic.status, SubscriptionStatus.PAST_DUE)


@freeze_time(utcnow_with_tz())
@tag('cloud')
class AutonomousLicenseManagerTest:
    product: Product

    stripe_subscription_patch = {
        'current_period_end': int((utcnow_with_tz() + relativedelta(months=1)).timestamp()),
        'cancel_at_period_end': True,
        'status': 'trialing',
        'items': {
            'data': [
                {
                    'price': {
                        'id': 'price_id',
                        'product': 'product_id',
                        'unit_amount': 2000,
                        'metadata': {
                            'title': 'channels'
                        }
                    },
                    'id': 'some_id',
                    'quantity': 1,
                    'metadata': {
                        'active': 'true'
                    }
                }
            ]
        }
    }

    @staticmethod
    @patch('licensing.payment.stripe.api.StripeAPI.get_or_create_customer', return_value='some_id')
    @patch('licensing.payment.stripe.api.StripeAPI.create_subscription',
           return_value={'id': 'subs_id', 'trial_end': (utcnow_with_tz() + timedelta(days=14)).timestamp(),
                         **stripe_subscription_patch})
    def _register_account(username: str, product: str, __get_or_create_customer, __create_subscription):
        user = User.objects.create_user(username=username, email=username, password='zaq11qaz')
        BillingAccount.get_or_create(username=username)
        lic = AutonomousLicenseManager.create(
            is_trial=False,
            product_name=AutonomousLicenseManager.ProductName(product),
            username=username
        )

        return user, lic

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            name=cls.product,
            config=products[cls.product]
        )
        cls.meter_attributes = list(cls.product.config['meter_attributes'].keys())
        cls.email = 'test@mail.com'
        cls.user, cls.license = cls._register_account(cls.email, cls.product.name)

    def test_create_license(self):

        time_with_period = utcnow_with_tz() + timedelta(days=self.product.period_in_days())
        self.assertAlmostEqual(self.license.expiration_date, time_with_period, delta=timedelta(seconds=10))
        self.assertEqual(self.license.product.name, self.product.name)
        self.assertFalse(self.license.is_trial)

        for attr in self.license.meter_attributes:
            attr_limit = self.product.config['meter_attributes'][attr.title]['limit']
            additional_properties = self.product.config['meter_attributes'][attr.title]['additional_properties']
            additional_properties = {key: None for key in additional_properties.keys()}
            self.assertEqual(attr.limit, attr_limit)
            self.assertEqual(attr.allowed, attr_limit)
            self.assertEqual(attr.uses, 0)
            self.assertEqual(attr.gross_uses, 0)
            self.assertEqual(attr.additional_properties, additional_properties)

    def test_check_meter_attribute(self):
        for attr in self.meter_attributes:
            self.assertTrue(AutonomousLicenseManager.check_meter_attribute(self.license.id, attr))

        if self.license.transactions.limit != -1:
            AutonomousLicenseManager.increment_meter_attribute(
                license_id=self.license.id,
                title='transactions',
                increment=self.product.config['meter_attributes']['transactions']['limit'])
            self.assertFalse(AutonomousLicenseManager.check_meter_attribute(self.license.id, 'transactions'))

    def test_increment_trial_license_attribute_not_exist(self):
        with self.assertRaises(LicenseAttributeNotExist) as ex:
            AutonomousLicenseManager.increment_meter_attribute(self.license.id, 'not_exist')

        self.assertEqual(ex.exception.__str__(), 'License meter-attribute "not_exist" does not exist')

    def test_increment_trial_license_limit_attribute(self):
        def increment_test(lic, attr: str):
            for _ in range(getattr(lic, attr).limit+1):
                AutonomousLicenseManager.increment_meter_attribute(lic.id, attr)

        for attr in self.license.meter_attributes:
            if attr.limit == -1:
                continue
            with self.assertRaises(LicenseLimitAttribute) as ex:
                increment_test(self.license, attr.title)

            self.assertEqual(ex.exception.__str__(), f'License attribute "{attr.title}" limit exceeded')

    def test_increment_meter_attributes(self):
        for source_attr in self.license.meter_attributes:
            modified_lic = AutonomousLicenseManager.increment_meter_attribute(self.license.id, source_attr.title)

            modified_attr = getattr(modified_lic, source_attr.title)

            self.assertEqual(modified_attr.uses, source_attr.uses + 1)
            self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses + 1)

            if source_attr.limit != -1:
                self.assertEqual(modified_attr.allowed, source_attr.allowed - 1)

    def test_decrement_license_attribute_not_exist(self):
        with self.assertRaises(LicenseAttributeNotExist) as ex:
            AutonomousLicenseManager.decrement_meter_attribute(self.license.id, 'some_license')

        self.assertEqual(ex.exception.__str__(), 'License meter-attribute "some_license" does not exist')

    def test_decrement_meter_attributes(self):
        for attr in self.license.meter_attributes:
            AutonomousLicenseManager.increment_meter_attribute(self.license.id, attr.title, 3)

        self.license.refresh_from_db()
        for source_attr in self.license.meter_attributes:
            modified_lic = AutonomousLicenseManager.decrement_meter_attribute(self.license.id, source_attr.title)

            modified_attr = getattr(modified_lic, source_attr.title)

            self.assertEqual(modified_attr.uses, source_attr.uses - 1)
            self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses)

            if source_attr.limit != -1:
                self.assertEqual(modified_attr.allowed, source_attr.allowed + 1)

    def test_is_valid_true(self):
        result = AutonomousLicenseManager.is_valid(self.license.id)
        self.assertTrue(result)

    def test_is_valid_false(self):
        self.license.expiration_date = utcnow_with_tz() - timedelta(minutes=1)
        self.license.save()
        result = AutonomousLicenseManager.is_valid(self.license.id)
        self.assertFalse(result)

    def test_get_all_active_licenses(self):
        user, lic = self._register_account('inactive@mail.com', self.product.name)

        with self.subTest('All active'):
            active_licenses = AutonomousLicenseManager.get_all_active_licenses()
            source_licenses = {self.license.id, lic.id}
            self.assertEqual(source_licenses, {lic.id for lic in active_licenses})

        with self.subTest('One inactive'):
            with transaction.atomic():
                lic.config['status'] = SubscriptionStatus.UNPAID.value
                lic.save()
            active_licenses = AutonomousLicenseManager.get_all_active_licenses()
            source_licenses = {self.license.id}
            self.assertEqual(source_licenses, {lic.id for lic in active_licenses})

    def test_delete_license(self):
        AutonomousLicenseManager.delete(self.license.id)

        with self.assertRaises(ObjectDoesNotExist):
            AutonomousLicenseManager._obtain_license(self.license.id)

    def test_reset_meter_attributes(self):
        lic = AutonomousLicenseManager.zero_metered_attributes(self.license.id)

        for attr in lic.meter_attributes:
            AutonomousLicenseManager.increment_meter_attribute(self.license.id, attr.title)

        for attr in lic.meter_attributes:
            self.assertEqual(attr.uses, 0)
            self.assertEqual(attr.gross_uses, 0)
            self.assertEqual(attr.allowed, attr.limit)

    def test_update_license(self):
        self.license.transactions = MeterAttribute(limit=500, title='transactions')
        new_expiration_date = self.license.expiration_date + timedelta(self.product.period_in_days())
        new_subscription_id = 'new_subscription_id'
        lic = AutonomousLicenseManager.update_license(
            license_id=self.license.id,
            cancel_at_period_end=True,
            subscription_id=new_subscription_id,
            expiration_date=new_expiration_date,
            metered_attributes=self.license.meter_attributes,
            status=SubscriptionStatus.PAST_DUE
        )

        self.assertTrue(lic.cancel_at_period_end)
        self.assertEqual(lic.subscription_id, 'new_subscription_id')
        self.assertEqual(lic.expiration_date, new_expiration_date)
        self.assertEqual(lic.transactions.limit, 500)
        self.assertEqual(lic.status, SubscriptionStatus.PAST_DUE)


@tag('cloud')
class BaseLicenseManagerTest:
    product: Product

    @staticmethod
    def _register_account(
            username: str,
            product: Product,
    ):
        user = User.objects.create_user(username=username, email=username, password='zaq11qaz')
        billing_account, _ = BillingAccount.get_or_create(username=username)
        lic = BaseLicenseManager.lic_object._create(
            billing_account=billing_account,
            product=product,
            subscription_id='subscription_id',
            expiration_date=utcnow_with_tz() + timedelta(days=product.period_in_days()),
            stripe_item_ids={attr: 'some_id' for attr in product.config['meter_attributes'].keys()},
        )

        return user, lic

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            name=cls.product,
            config=products[cls.product]
        )
        cls.email = 'test@mail.com'
        cls.user, cls.license = cls._register_account(cls.email, cls.product)

    def test_check_meter_attribute(self):
        for attr in self.license.meter_attributes:
            self.assertTrue(BaseLicenseManager.check_meter_attribute(self.license, attr.title))

    def test_increment_license_attribute_not_exist(self):
        with self.assertRaises(LicenseAttributeNotExist) as ex:
            BaseLicenseManager.increment_meter_attribute(self.license, 'not_exist')

        self.assertEqual(ex.exception.__str__(), 'License meter-attribute "not_exist" does not exist')

    def test_increment_meter_attributes(self):
        for source_attr in self.license.meter_attributes:
            modified_lic = BaseLicenseManager.increment_meter_attribute(self.license, source_attr.title)

            modified_attr = getattr(modified_lic, source_attr.title)

            self.assertEqual(modified_attr.uses, source_attr.uses + 1)
            self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses + 1)

    def test_decrement_license_attribute_not_exist(self):
        with self.assertRaises(LicenseAttributeNotExist) as ex:
            BaseLicenseManager.decrement_meter_attribute(self.license, 'attr')

        self.assertEqual(ex.exception.__str__(), 'License meter-attribute "attr" does not exist')

    def test_decrement_meter_attributes(self):
        for attr in self.license.meter_attributes:
            BaseLicenseManager.increment_meter_attribute(self.license, attr.title, 3)

        self.license.refresh_from_db()

        for source_attr in self.license.meter_attributes:
            modified_lic = BaseLicenseManager.decrement_meter_attribute(self.license, source_attr.title)

            modified_attr = getattr(modified_lic, source_attr.title)

            self.assertEqual(modified_attr.uses, source_attr.uses - 1)
            self.assertEqual(modified_attr.gross_uses, source_attr.gross_uses)

    def test_is_valid_true(self):
        result = BaseLicenseManager.is_valid(self.license)
        self.assertTrue(result)

    def test_is_valid_false(self):
        self.license.expiration_date = utcnow_with_tz() - timedelta(minutes=1)
        self.license.save()
        result = BaseLicenseManager.is_valid(self.license)
        self.assertFalse(result)

    def test_delete_license(self):
        BaseLicenseManager.delete(self.license)
        self.assertIsNone(self.license.id)

    def test_reset_meter_attributes(self):
        lic = BaseLicenseManager.zero_metered_attributes(self.license)

        for attr in lic.meter_attributes:
            BaseLicenseManager.increment_meter_attribute(lic, attr.title)

        for attr in lic.meter_attributes:
            self.assertEqual(attr.uses, 0)
            self.assertEqual(attr.gross_uses, 0)
            self.assertEqual(attr.allowed, attr.limit)


def init_test_case(class_: type, product_names: List[str]):
    # init test case for each product
    for product in product_names:
        class_name = f'{class_.__name__}{product}'
        cls = type(class_name, (class_, TestCase), {'product': product})
        globals()[class_name] = cls


# TODO: add platform-cloud-pro
init_test_case(WorkspaceLicenseManagerTest, ['platform-cloud-basic'])
init_test_case(AutonomousLicenseManagerTest,
               ['image-api-base', 'image-api-startup', 'image-api-expert', 'image-api-advanced'])
init_test_case(BaseLicenseManagerTest,
               ['platform-cloud-basic', 'platform-cloud-pro', 'image-api-base',
                'image-api-startup', 'image-api-expert', 'image-api-advanced'])
