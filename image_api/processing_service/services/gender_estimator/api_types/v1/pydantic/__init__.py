# METABASE
from typing import List, Optional

from pydantic import BaseModel, Extra, Field
from settings import IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT, OBJECTS_KEY

SampleObjectInput = dict
if IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT:
    SampleObject = dict
else:
    from api.types.v1.pydantic.sample_object import SampleObject


class Sample(BaseModel):
    image: str = Field(alias="$image", description='The Base64 representation of your binary image data')
    objects: List[SampleObject] = Field(alias=OBJECTS_KEY, title='objects')

    class Config:
        allow_population_by_field_name = True
        extra = Extra.allow


class SampleInput(Sample):
    objects: Optional[List[SampleObjectInput]] = Field(title='objects')
