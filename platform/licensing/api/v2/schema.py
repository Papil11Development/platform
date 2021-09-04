import strawberry

from licensing.api.v2.mutations import InternalMutation
from licensing.api.v2.queries import InternalQuery

internal_schema = strawberry.Schema(query=InternalQuery, mutation=InternalMutation)
