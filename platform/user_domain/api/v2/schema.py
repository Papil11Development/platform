import strawberry

from user_domain.api.v2.mutations import InternalMutation, Mutation
from user_domain.api.v2.queries import Query, InternalQuery

internal_schema = strawberry.Schema(query=InternalQuery, mutation=InternalMutation)
schema = strawberry.Schema(query=Query, mutation=Mutation)
