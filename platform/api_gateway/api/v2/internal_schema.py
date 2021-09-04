import strawberry
from strawberry.tools import merge_types

from django.conf import settings

from user_domain.api.v2 import schema as user_schema
from licensing.api.v2 import schema as license_schema

queries = (user_schema.InternalQuery, license_schema.InternalQuery,)
mutations = (user_schema.InternalMutation, license_schema.InternalMutation,)

Query = merge_types("Query", queries)
Mutation = merge_types("Mutation", mutations)

schema = strawberry.Schema(query=Query, mutation=Mutation)
