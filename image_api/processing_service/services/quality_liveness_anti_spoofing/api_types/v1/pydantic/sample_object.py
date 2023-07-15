from typing import List, Literal, Optional
from pydantic import BaseModel, Extra, Field


class Liveness(BaseModel):
    confidence: float = Field(example=0.5067038536071777, description='Confidence')
    value: Literal['REAL',
                   'FAKE'] = Field(example='REAL', description='Liveness value')


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the face in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')
    liveness: Liveness

    class Config:
        extra = Extra.allow


class BaseObject(BaseModel):
    id: int = Field(description='The ordinal number of the face in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')

    class Config:
        extra = Extra.allow
