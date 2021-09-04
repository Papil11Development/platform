import strawberry

from user_domain.api.v1 import schema as user_schema

schema = strawberry.Schema(query=user_schema.InternalQuery, mutation=user_schema.InternalMutation)
