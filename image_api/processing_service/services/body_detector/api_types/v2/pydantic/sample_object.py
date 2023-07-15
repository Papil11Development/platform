from typing import List, Literal

from pydantic import BaseModel, Extra, Field


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the body in the image', ge=0)
    class_: str = Field(alias='class', example='body', description='Object class name')
    confidence: float = Field(example=0.69044026635, description='Confidence')
    bbox: List[float] = Field(
        example=[
            0.42242398858070374,
            0.05838850140571594,
            0.5360375642776489,
            0.17216356098651886
        ],
        description='Bounding box of detected body'
    )

    class Config:
        extra = Extra.allow
