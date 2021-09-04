import traceback

from django.core.management import BaseCommand
from notification_domain.models import Trigger
from user_domain.models import Workspace


class Command(BaseCommand):
    def handle(self, *args, **options):
        workspaces = Workspace.objects.prefetch_related("triggers", "labels").all()
        triggers_to_create = []

        for workspace in workspaces:
            try:
                create = True

                for trigger in workspace.triggers.all():
                    if "variables" in trigger.meta.keys():
                        create = False
                        break

                if not create:
                    continue

                labels_list = list(workspace.labels.all())

                try:
                    vip_label = next(filter(lambda x: x.title == 'VIP', labels_list), None).id
                    shoplifter_label = next(filter(lambda x: x.title == 'Shoplifter', labels_list), None).id
                except AttributeError:
                    raise Exception(f"No Shoplifter or VIP label in workspace with id: {workspace.id}")

                triggers_to_create.append(Trigger(workspace=workspace,
                                                  meta=self.get_trigger_presence_meta(str(vip_label))))
                triggers_to_create.append(Trigger(workspace=workspace,
                                                  meta=self.get_trigger_presence_meta(str(shoplifter_label))))
            except Exception as exception:
                print("*" * 100)
                print(f"Something wrong in workspace with id: {workspace.id} \nException: {exception} \n")
                traceback.print_exc()
                continue

        Trigger.objects.bulk_create(triggers_to_create, batch_size=100)

    @staticmethod
    def get_trigger_presence_meta(label_uuid: str):
        return {
            "variables": {"0_v": {"type": "presence",
                                  "target": [{"type": "Label", "uuid": label_uuid}],
                                  "target_limit": 0,
                                  "target_operation": ">"}
                          }
        }
