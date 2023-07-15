from pydantic import BaseModel, Extra, Field


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the body in the image', ge=0)
    class_: str = Field(alias='class', example='face', description='Object class name')
    age: int = Field(example=25, description='Age')

    class Config:
        extra = Extra.allow
