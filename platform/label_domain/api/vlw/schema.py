from label_domain.api.vlw.mutations import Mutation
from label_domain.api.vlw.queries import Query
import strawberry


schema = strawberry.Schema(query=Query, mutation=Mutation)
