import strawberry
from strawberry.tools import merge_types

from api_gateway.api.extensions import AuthorizationExtension
from label_domain.api.vLuna import schema as label_schema
from data_domain.api.vLuna import schema as data_schema
from person_domain.api.vLuna import schema as person_schema
from user_domain.api.vLuna import schema as user_schema

InternalQuery = merge_types("Query", (user_schema.Query,
                                      data_schema.Query,
                                      label_schema.Query,
                                      person_schema.Query))
InternalMutation = merge_types("Mutation", (label_schema.Mutation,
                                            person_schema.Mutation,
                                            data_schema.Mutation,))

schema = strawberry.Schema(query=InternalQuery, mutation=InternalMutation,
                           extensions=[AuthorizationExtension])
