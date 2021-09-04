import strawberry

from data_domain.api.v2.mutations import Mutation
from data_domain.api.v2.queries import Query

schema = strawberry.Schema(query=Query, mutation=Mutation)
