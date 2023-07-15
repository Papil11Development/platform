import os
from typing import List

from pydantic import BaseModel, Extra, Field

RECOGNIZER_CONFIG = os.environ.get('RECOGNIZER_CONFIG')
version, weight = RECOGNIZER_CONFIG \
    .replace('method', '') \
    .replace('_recognizer.xml', '') \
    .split('v')


class BSM(BaseModel):
    blob: str = Field(alias="blob", description='The Base64 representation of your binary biometric template data')
    format: str = "NDARRAY"
    dtype: str = "uint8_t"
    shape: List[int] = Field(alias="shape", description='The size of vector', min_items=1, max_items=1)


class Template(BaseModel):
    face_template_extractor: BSM = Field(alias=f"_face_template_extractor_{weight}_{version}", description='BSM biometric template')


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
    template: Template = Field(alias="template", description='Binary biometric template')

    class Config:
        extra = Extra.allow
