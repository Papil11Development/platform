from typing import List

from pydantic import BaseModel, Extra, Field


class Fitter(BaseModel):
    fitter_type: str = Field(example='fda', description='Fitter type')
    keypoints: List[float] = Field(description='Keypoints', min_items=63, max_items=63)
    left_eye: List[float] = Field(description='Left eye', min_items=2, max_items=2)
    right_eye: List[float] = Field(description='Right eye', min_items=2, max_items=2)


class Angles(BaseModel):
    yaw: float = Field(description='Yaw')
    roll: float = Field(description='Roll')
    pitch: float = Field(description='Pitch')


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
    fitter: Fitter
    angles: Angles

    class Config:
        extra = Extra.allow
