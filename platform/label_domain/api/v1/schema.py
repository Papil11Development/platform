from label_domain.api.v1.mutations import Mutation
from label_domain.api.v1.queries import Query
import strawberry


schema = strawberry.Schema(query=Query, mutation=Mutation)
