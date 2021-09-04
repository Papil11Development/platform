from person_domain.api.vLuna.mutations import Mutation
from person_domain.api.vLuna.queries import Query
import strawberry


schema = strawberry.Schema(query=Query, mutation=Mutation)
