import strawberry
from strawberry.tools import merge_types

from label_domain.api.v1 import schema as label_schema
from data_domain.api.v1 import schema as data_schema
from collector_domain.api.v1 import schema as collector_schema
from person_domain.api.v1 import schema as person_schema
from notification_domain.api.v1 import schema as notification_schema
from user_domain.api.v1 import schema as user_schema

from api_gateway.api.extensions import TriggerExtension

Query = merge_types("Query", (label_schema.Query,
                              user_schema.Query,
                              collector_schema.Query,
                              person_schema.Query,
                              data_schema.Query,
                              notification_schema.Query))
Mutation = merge_types("Mutation", (label_schema.Mutation,
                                    collector_schema.Mutation,
                                    person_schema.Mutation,
                                    notification_schema.Mutation))

schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=[TriggerExtension])
