from user_domain.api.vLuna.queries import Query
import strawberry


schema = strawberry.Schema(query=Query)
