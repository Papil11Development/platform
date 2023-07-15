import strawberry
from data_domain.api.v3 import schema as data_schema

schema = strawberry.Schema(query=data_schema.Query)
