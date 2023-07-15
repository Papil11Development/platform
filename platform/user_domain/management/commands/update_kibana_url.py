from django.core.management import BaseCommand
from django.db import transaction

from user_domain.models import Workspace
from main.settings import PUBLIC_KIBANA_URL


class Command(BaseCommand):
    def handle(self, *args, **options):
        for ws_id in Workspace.objects.filter().values_list('id', flat=True):
            with transaction.atomic():
                locked_ws = Workspace.objects.select_for_update().get(id=ws_id)
                features = locked_ws.config.get('features', {})
                for analytics_type in ['retail_analytics', 'advertising_analytics']:
                    if not features.get(analytics_type, {}).get('url'):
                        continue
                    dashboard_path = features[analytics_type]["url"].split("/s/", 1)[-1]
                    url = f'{PUBLIC_KIBANA_URL}/s/{dashboard_path}'
                    features[analytics_type]['url'] = url
                locked_ws.config.update({'features': features})
                locked_ws.save()
