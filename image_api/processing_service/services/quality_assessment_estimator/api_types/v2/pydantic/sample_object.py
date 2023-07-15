from typing import List

from pydantic import BaseModel, Extra, Field


class Quality(BaseModel):
    total_score: int = Field(description='Total score')
    is_sharp: bool
    sharpness_score: int = Field(description='Sharpness score')
    is_evenly_illuminated: bool
    illumination_score: int = Field(description='Illumination score')
    no_flare: bool
    is_left_eye_opened: bool
    left_eye_openness_score: int = Field(description='Left eye opened score')
    is_right_eye_opened: bool
    right_eye_openness_score: int = Field(description='Right eye opened score')
    is_rotation_acceptable: bool
    max_rotation_deviation: int = Field(description='Max rotation deviation')
    not_masked: bool
    not_masked_score: int = Field(description='Not masked score')
    is_neutral_emotion: bool
    neutral_emotion_score: int = Field(description='Neutral emotion score')
    is_eyes_distance_acceptable: bool
    eyes_distance: int = Field(description='Eyes distance')
    is_margins_acceptable: bool
    margin_outer_deviation: int = Field(description='Margin outer deviation')
    margin_inner_deviation: int = Field(description='Margin inner deviation')
    is_not_noisy: bool
    noise_score: int = Field(description='Noise score')
    watermark_score: int = Field(description='Watermark score')
    has_watermark: bool
    dynamic_range_score: int = Field(description='Dynamic range score')
    is_dynamic_range_acceptable: bool
    background_uniformity_score: int = Field(description='Background uniformity score')
    is_background_uniform: bool


class SampleObject(BaseModel):
    id: int = Field(description='The ordinal number of the face in the image')
    class_: str = Field(alias='class', example='face', description='Object class name')
    confidence: float = Field(example=0.69044026635, description='Confidence')
    bbox: List[float] = Field(
        example=[
            0.42242398858070374,
            0.05838850140571594,
            0.5360375642776489,
            0.17216356098651886
        ],
        description='Bounding box'
    )
    quality: Quality

    class Config:
        extra = Extra.allow
