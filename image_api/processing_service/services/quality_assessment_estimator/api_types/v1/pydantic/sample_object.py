from typing import List

from pydantic import BaseModel, Extra, Field


class QAA(BaseModel):
    totalScore: int = Field(description='Total score')
    isSharp: bool
    sharpnessScore: int = Field(description='Sharpness score')
    isEvenlyIlluminated: bool
    illuminationScore: int = Field(description='Illumination score')
    noFlare: bool
    isLeftEyeOpened: bool
    leftEyeOpennessScore: int = Field(description='Left eye opened score')
    isRightEyeOpened: bool
    rightEyeOpennessScore: int = Field(description='Right eye opened score')
    isRotationAcceptable: bool
    maxRotationDeviation: int = Field(description='Max rotation deviation')
    notMasked: bool
    notMaskedScore: int = Field(description='Not masked score')
    isNeutralEmotion: bool
    neutralEmotionScore: int = Field(description='Neutral emotion score')
    isEyesDistanceAcceptable: bool
    eyesDistance: int = Field(description='Eyes distance')
    isMarginsAcceptable: bool
    marginOuterDeviation: int = Field(description='Margin outer deviation')
    marginInnerDeviation: int = Field(description='Margin inner deviation')
    isNotNoisy: bool
    noiseScore: int = Field(description='Noise score')
    watermarkScore: int = Field(description='Watermark score')
    hasWatermark: bool
    dynamicRangeScore: int = Field(description='Dynamic range score')
    isDynamicRangeAcceptable: bool
    backgroundUniformityScore: int = Field(description='Background uniformity score')
    isBackgroundUniform: bool


class Quality(BaseModel):
    qaa: QAA


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
