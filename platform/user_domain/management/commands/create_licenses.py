import logging
import time

from django.core.management import BaseCommand

from licensing.common_managers import LicenseManagerCommon
from licensing.managers import WorkspaceLicenseManager
from licensing.models import BillingAccount
from main import settings
from platform_lib.exceptions import LicenseNotExist
from user_domain.models import Access

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        if options['rollback']:
            self.rollback()
        else:
            self.create_standalone_licenses()

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--rollback',
            action='store_true',
            help='Delete created licenses',
        )

    @staticmethod
    def create_standalone_licenses():
        time1 = time.time()
        # Add license for standalone users and create it on stripe
        # Change user's access from Admin to Owner
        accesses = Access.objects.select_related('user', 'workspace').filter(
            user__groups__name=settings.STANDALONE_GROUP, user__billing_account__isnull=True, user__is_superuser=False
        )
        for access in accesses:
            user = access.user
            LicenseManagerCommon.create_billing_account(user.username)
            workspace = access.workspace
            LicenseManagerCommon(str(workspace.id)).create_workspace(user.username)
            LicenseManagerCommon.create_image_api_license(user.username)

        logger.info(f"Updated users count: {accesses.count()}")
        accesses.update(permissions='OW')
        logger.info(f"Migration time: {time.time() - time1}")

    @staticmethod
    def rollback():
        accesses = Access.objects.select_related('user', 'workspace').filter(
            user__groups__name=settings.STANDALONE_GROUP, user__billing_account__isnull=False, user__is_superuser=False
        )
        deleted_licenses = 0
        for access in accesses:
            try:
                if WorkspaceLicenseManager.delete(str(access.workspace.id)):
                    BillingAccount.objects.get(user_id=access.user.id).delete()
                    deleted_licenses += 1
            except LicenseNotExist:
                logger.error(f'User without license: {access.user.username}')
                continue
        accesses_count = accesses.count()  # do not call count after update, number will be changed
        accesses.update(permissions='AD')

        if accesses_count != deleted_licenses:
            logger.error(f'Rollback "{__name__}" failed!\n'
                         f'\tUpdated Accesses: {accesses_count}.\n'
                         f'\tDeleted Licenses: {deleted_licenses}.')
            raise Exception('Deleted licenses count not equals to selected licenses count')  # for migration rollback
