import os
import django
import strawberry

from data_domain.api.v2.mutations import Mutation as Mutation_v2


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


@strawberry.type
class Mutation(Mutation_v2):
    pass
