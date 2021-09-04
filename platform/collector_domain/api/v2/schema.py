import strawberry

from collector_domain.api.v2.mutations import AgentMutation as Mutation
from collector_domain.api.v2.queries import Query

schema = strawberry.Schema(query=Query, mutation=Mutation)
