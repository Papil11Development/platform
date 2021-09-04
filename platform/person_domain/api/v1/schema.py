from person_domain.api.v1.mutations import Mutation
from person_domain.api.v1.queries import Query
import strawberry


schema = strawberry.Schema(query=Query, mutation=Mutation)
