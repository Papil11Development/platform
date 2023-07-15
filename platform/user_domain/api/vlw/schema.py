from user_domain.api.vlw.queries import Query
import strawberry


schema = strawberry.Schema(query=Query)
