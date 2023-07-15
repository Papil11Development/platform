from typing import List, Literal
from pydantic import BaseModel, Extra, Field


class Liveness(BaseModel):
    confidence: float = Field(example=0.5067038536071777, description='Confidence')
    value: Literal['NOT_ENOUGH_DATA', 'REAL', 'FAKE'] = Field(example='REAL', description='Liveness value')


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the face in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')
    confidence: float = Field(example=0.8801844120025635, description='Confidence')
    bbox: List[float] = Field(
        example=[
            0.42242398858070374,
            0.05838850140571594,
            0.5360375642776489,
            0.17216356098651886
        ],
        description='Bounding box of detected face'
    )
    liveness: Liveness

    class Config:
        extra = Extra.allow
