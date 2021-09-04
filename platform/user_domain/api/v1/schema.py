import strawberry
from user_domain.api.v1.queries import InternalQuery, Query
from user_domain.api.v1.mutations import InternalMutation


internal_schema = strawberry.Schema(query=InternalQuery, mutation=InternalMutation)
schema = strawberry.Schema(query=Query)
