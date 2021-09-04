from django.core.management import BaseCommand
from django.db import transaction

from user_domain.models import Workspace


class Command(BaseCommand):
    def handle(self, *args, **options):
        for ws_id in Workspace.objects.filter().values_list('id', flat=True):
            with transaction.atomic():
                locked_ws = Workspace.objects.select_for_update().get(id=ws_id)
                features = locked_ws.config.get('features', {})
                if features.get('retail_analytics'):
                    continue

                features['retail_analytics'] = {
                    'enabled': True,
                    'url': locked_ws.config.get('url_elk'),
                    'index': locked_ws.config.get('elk_index_id')
                }
                locked_ws.config.update({'features': features})
                locked_ws.save()
