from typing import List, Optional

from pydantic import BaseModel, Extra, Field
from settings import IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT, OBJECTS_KEY

SampleObjectInput = dict
if IS_SCHEMELESS_SAMPLE_OBJECT_OUTPUT:
    SampleObject = dict
else:
    from api.types.v1.pydantic.sample_object import SampleObject


class Verification(BaseModel):
    distance: float = Field(description='Distance')
    fa_r: float = Field(description='False Acceptance Rate')
    fr_r: float = Field(description='False Rejection Rate')
    score: float = Field(description='Score')


class ISample(BaseModel):
    objects: List[SampleObject] = Field(alias=OBJECTS_KEY, title='objects')

    class Config:
        allow_population_by_field_name = True
        extra = Extra.allow


class Sample(ISample):
    verification: Verification


class SampleInput(ISample):
    objects: Optional[List[SampleObjectInput]] = Field(title='objects')
