from django.apps import AppConfig


class DataDomainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'data_domain'

    def ready(self):
        # for signal init
        import data_domain.signals
