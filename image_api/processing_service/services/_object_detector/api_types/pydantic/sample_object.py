from typing import List, Literal

from pydantic import BaseModel, Extra, Field

class_literals = ("body", "bicycle", "car", "motorcycle", "bus", "train", "truck", "traffic_light", "fire_hydrant",
                  "stop_sign", "bird", "cat", "dog", "horse", "sheep", "cow", "bear", "backpack", "umbrella",
                  "handbag", "suitcase", "sports_ball", "baseball_bat", "skateboard", "tennis_racket", "bottle",
                  "wine_glass", "cup", "fork", "knife", "laptop", "phone", "book", "scissors")


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the object in the image', ge=0)
    class_: Literal[class_literals] = Field(alias='class', example='body', description='Object class name')
    confidence: float = Field(example=0.69044026635, description='Confidence')
    bbox: List[float] = Field(
        example=[
            0.42242398858070374,
            0.05838850140571594,
            0.5360375642776489,
            0.17216356098651886
        ],
        description='Bounding box of detected object'
    )

    class Config:
        extra = Extra.allow
