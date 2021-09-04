from label_domain.api.vLuna.mutations import Mutation
from label_domain.api.vLuna.queries import Query
import strawberry


schema = strawberry.Schema(query=Query, mutation=Mutation)
