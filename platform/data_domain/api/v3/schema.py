import strawberry

from data_domain.api.v3.queries import Query

schema = strawberry.Schema(query=Query)
