import strawberry
from user_domain.api.v2.queries import Query as Query_v2


@strawberry.type
class Query(Query_v2):
    pass
