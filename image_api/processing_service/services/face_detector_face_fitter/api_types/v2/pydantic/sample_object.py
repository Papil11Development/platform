from typing import List

from pydantic import BaseModel, Extra, Field


class Point(BaseModel):
    proj: List[float] = Field(description='Keypoint')


class Keypoints(BaseModel):
    left_eye_brow_left: Point = Field(description='Keypoint of left eye brow left')
    left_eye_brow_up: Point = Field(description='Keypoint of left eye brow up')
    left_eye_brow_right: Point = Field(description='Keypoint of left eye brow right')
    right_eye_brow_left: Point = Field(description='Keypoint of right eye brow left')
    right_eye_brow_up: Point = Field(description='Keypoint of right eye brow up')
    right_eye_brow_right: Point = Field(description='Keypoint of right eye brow right')
    left_eye_left: Point = Field(description='Keypoint of left eye left')
    left_eye: Point = Field(description='Keypoint of left eye')
    left_eye_right: Point = Field(description='Keypoint of left eye right')
    right_eye_left: Point = Field(description='Keypoint of right eye left')
    right_eye: Point = Field(description='Keypoint of right eye')
    right_eye_right: Point = Field(description='Keypoint of right eye right')
    left_ear_bottom: Point = Field(description='Keypoint of left ear bottom')
    nose_left: Point = Field(description='Keypoint of nose left')
    nose: Point = Field(description='Keypoint of nose')
    nose_right: Point = Field(description='Keypoint of nose right')
    right_ear_bottom: Point = Field(description='Keypoint of right ear bottom')
    mouth_left: Point = Field(description='Keypoint of mouth left')
    mouth: Point = Field(description='Keypoint of mouth')
    mouth_right: Point = Field(description='Keypoint of mouth right')
    chin: Point = Field(description='Keypoint of chin')


class Pose(BaseModel):
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
    keypoints: Keypoints = Field(description='Keypoints')
    pose: Pose

    class Config:
        extra = Extra.allow
