import logging
import uuid
from abc import ABC
from typing import Optional, Union, TYPE_CHECKING

from celery import shared_task, Task
from django.db import transaction

from licensing.managers import MeterAttributeManager, BaseLicenseManager, WorkspaceLicenseManager
from licensing.models import License
from licensing.payment.stripe.api import StripeAPI
from licensing.utils import timestamp_for_send_usage
from platform_lib.exceptions import StripeException

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


@shared_task
def reset_gross_uses():
    licenses = WorkspaceLicenseManager.get_all_licenses()

    with transaction.atomic():
        for lic in licenses.select_for_update(of=('self',)):
            updated = False
            for attribute in lic.meter_attributes:
                if attribute.gross_uses != attribute.uses:
                    attribute.gross_uses = attribute.uses
                    lic.set_meter_attribute(attribute.title, attribute)
                    updated = True

            if updated:
                lic.save()


class SendingUsageRecordsTask(Task, ABC):

    def on_success(self, retval, task_id, args, kwargs):
        # reset gross_uses if task was call periodically
        if not kwargs.get('license_id'):
            reset_gross_uses.delay()


@shared_task(base=SendingUsageRecordsTask)
def send_usage_records(license_id: Optional[Union[str, uuid.UUID]] = None):
    licenses = BaseLicenseManager.get_all_active_licenses().select_related(
        'billing_account__user', 'product').prefetch_related('billing_account__user__groups')  # type: QuerySet[License]
    if license_id:
        licenses = licenses.filter(id=license_id)

    for lic in licenses:
        stripe_api = StripeAPI(lic.billing_account)

        for attribute in lic.meter_attributes:
            try:
                stripe_item_id, uses = MeterAttributeManager.prepare_meter_info_for_report(lic, attribute)
                usage_timestamp = timestamp_for_send_usage(lic)
            except Exception as ex:
                logger.error(msg=f"Broken license {lic.id}\nMessage: {str(ex)}")
                continue

            try:
                stripe_api.send_usage_records(stripe_item_id, uses, 'set', usage_timestamp)
            except StripeException as ex:
                logger.error(msg=f"Failed send usage records for {lic.id}\nMessage: {str(ex)}")
                continue
