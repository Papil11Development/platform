from pydantic import BaseModel, Extra, Field


class Mask(BaseModel):
    confidence: float = Field(example=0.5067038536071777, description='Confidence')
    value: bool = Field(example=True, description='Is masked boolean value')


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the face in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')
    has_medical_mask: Mask

    class Config:
        extra = Extra.allow
