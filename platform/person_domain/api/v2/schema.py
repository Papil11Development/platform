from person_domain.api.v2.mutations import Mutation
from person_domain.api.v2.queries import Query
import strawberry


schema = strawberry.Schema(query=Query, mutation=Mutation)
