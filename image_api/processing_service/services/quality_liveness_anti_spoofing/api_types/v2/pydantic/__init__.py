from typing import List, Optional, Union

from pydantic import BaseModel, Extra, Field
from settings import IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT, OBJECTS_KEY

SampleObjectInput = dict
if IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT:
    SampleObject = dict
else:
    from api.types.v2.pydantic.sample_object import SampleObject, BaseObject


class BSM(BaseModel):
    blob: str = Field(alias="blob", description='The Base64 representation of your binary image data')
    format: str = "IMAGE"


class Sample(BaseModel):
    image: BSM = Field(alias="_image", description='The blob with meta information')
    objects: List[Union[SampleObject, BaseObject]] = Field(alias=OBJECTS_KEY, title='objects')

    class Config:
        allow_population_by_field_name = True
        extra = Extra.allow


class SampleInput(Sample):
    objects: Optional[List[SampleObjectInput]] = Field(title='objects')
