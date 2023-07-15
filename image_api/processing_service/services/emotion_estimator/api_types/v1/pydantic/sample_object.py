from typing import List, Literal, Optional

from pydantic import BaseModel, Extra, Field


class Emotion(BaseModel):
    confidence: float = Field(example=0.8801844120025635, description='Confidence')
    emotion: Literal['ANGRY', 'DISGUSTED', 'SCARED', 'HAPPY', 'NEUTRAL', 'SAD', 'SURPRISED']


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the object in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')
    emotions: List[Emotion]

    class Config:
        extra = Extra.allow
