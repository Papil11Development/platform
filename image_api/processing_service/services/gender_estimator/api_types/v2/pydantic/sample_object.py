from typing import Literal

from pydantic import BaseModel, Extra, Field


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the face in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')
    gender: Literal['male', 'female'] = Field(description='Gender')

    class Config:
        extra = Extra.allow
