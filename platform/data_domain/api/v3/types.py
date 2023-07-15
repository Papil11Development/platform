from typing import List

import strawberry
from strawberry.scalars import JSON


@strawberry.type(description="Information about anthropometric points")
class Fitter:
    @strawberry.field(description="Type of set of anthropometric points."
                                  " The fda provides high accuracy in a wide range of facial angles"
                                  " (up to the full profile), however,"
                                  " the recognition algorithms still require that the facial perspective is as close to"
                                  " the full face as possible. The fda set contains 21 points")
    def fitter_type(self) -> str:
        return self.get('fitter_type')

    @strawberry.field(description="Facial anthropometric points."
                                  " List of repeated X, Y and Z coordinates relative to the original image")
    def keypoints(self) -> List[float]:
        return self.get('keypoints')

    @strawberry.field(description="Left eye center X and Y coordinates relative to the original image")
    def left_eye(self) -> List[float]:
        return self.get('left_eye')

    @strawberry.field(description="Right eye center X and Y coordinates relative to the original image")
    def right_eye(self) -> List[float]:
        return self.get('right_eye')


@strawberry.type(description="Information about emotions estimation")
class Emotions:
    @strawberry.field(description="Numerical value of manifestation of each estimated emotion")
    def confidence(self) -> float:
        return self.get('confidence')

    @strawberry.field(description="Emotion type: angry, disgusted, scared, happy, neutral, sad, surprised")
    def emotion(self) -> str:
        return self.get('emotion')


@strawberry.type(description="Estimation of face mask presence")
class MaskConfidenceValue:
    @strawberry.field(description="Numerical value of confidence that a person in the image is/isn’t wearing a mask")
    def confidence(self) -> float:
        return self.get('confidence')

    @strawberry.field(description="Verdict: true - masked person, false - unmasked person")
    def value(self) -> bool:
        return self.get('value')


@strawberry.type(description="Information about liveness estimation")
class LivenessConfidenceValue:
    @strawberry.field(description="Numerical value of confidence that the image belongs to a real person")
    def confidence(self) -> float:
        return self.get('confidence')

    @strawberry.field(description="Verdict: REAL - the face image belongs to a real person,"
                                  " FAKE - the face image doesn’t belong to a real person")
    def value(self) -> str:
        return self.get('value')


@strawberry.type(description="Information about biometric templates")
class Templates:
    @strawberry.field(description="Template version 11v1000")
    def template11v1000(self) -> str:
        return self.get('$template11v1000')


@strawberry.type(description="Head rotation angles in degrees")
class Angles:
    @strawberry.field(description="Rotation around the vertical axis Y")
    def yaw(self) -> str:
        return self.get('yaw')

    @strawberry.field(description="Rotation around the horizontal axis X")
    def roll(self) -> str:
        return self.get('roll')

    @strawberry.field(description="Rotation around the horizontal axis Z")
    def pitch(self) -> str:
        return self.get('pitch')


@strawberry.type(description="Quality assessment algorithm operates with the following data:"
                             " Qaa Data related to operation of quality assessment algorithm")
class Qaa:
    @strawberry.field(description="Numerical value that represents the score of overall image quality from 0 to 100")
    def total_score(self) -> int:
        return self.get('total_score')

    @strawberry.field(description="Boolean value that represents the image sharpness")
    def is_sharp(self) -> bool:
        return self.get('is_sharp')

    @strawberry.field(description="Numerical value that represents the sharpness score from 0 to 100")
    def sharpness_score(self) -> int:
        return self.get('sharpness_score')

    @strawberry.field(description="Boolean value that represents the illumination uniformity in the image")
    def is_evenly_illuminated(self) -> bool:
        return self.get('is_evenly_illuminated')

    @strawberry.field(description="Numerical value that represents the illumination uniformity score from 0 to 100")
    def illumination_score(self) -> int:
        return self.get('illumination_score')

    @strawberry.field(description="Boolean value that represents presence/absence of image flares")
    def no_flare(self) -> bool:
        return self.get('no_flare')

    @strawberry.field(description="Boolean value that represents the position of left eye (open/closed)")
    def is_left_eye_opened(self) -> bool:
        return self.get('is_left_eye_opened')

    @strawberry.field(description="Numerical value that represents"
                                  " the degree of left eye openness in points from 0 to 100")
    def left_eye_openness_score(self) -> int:
        return self.get('left_eye_openness_score')

    @strawberry.field(description="Boolean value that represents the position of right eye (open/closed)")
    def is_right_eye_opened(self) -> bool:
        return self.get('is_right_eye_opened')

    @strawberry.field(description="Numerical value that"
                                  " represents the degree of right eye openness in points from 0 to 100")
    def right_eye_openness_score(self) -> int:
        return self.get('right_eye_openness_score')

    @strawberry.field(description="Boolean value for acceptable/unacceptable values of yaw, pitch and roll angles")
    def is_rotation_acceptable(self) -> bool:
        return self.get('is_rotation_acceptable')

    @strawberry.field(description="Numerical value that represents"
                                  " the maximum degree of deviation for yaw, pitch and roll angles")
    def max_rotation_deviation(self) -> int:
        return self.get('max_rotation_deviation')

    @strawberry.field(description="Boolean value for presence/absence of face mask")
    def not_masked(self) -> bool:
        return self.get('not_masked')

    @strawberry.field(description="Numerical value of confidence"
                                  " that a person in the image isn’t wearing a mask in points from 0 to 100")
    def not_masked_score(self) -> int:
        return self.get('not_masked_score')

    @strawberry.field(description="Boolean value for presence/absence of neutral emotions")
    def is_neutral_emotion(self) -> bool:
        return self.get('is_neutral_emotion')

    @strawberry.field(description="Numerical value for score of neutral emotions in points from 0 to 100")
    def neutral_emotion_score(self) -> int:
        return self.get('neutral_emotion_score')

    @strawberry.field(description="Boolean value that represents the allowable/unallowable distance between eyes")
    def is_eyes_distance_acceptable(self) -> bool:
        return self.get('is_eyes_distance_acceptable')

    @strawberry.field(description="Numerical value that represents the distance between eyes in pixels")
    def eyes_distance(self) -> int:
        return self.get('eyes_distance')

    @strawberry.field(description="Boolean value that represents allowable/unallowable margins")
    def is_margins_acceptable(self) -> bool:
        return self.get('is_margins_acceptable')

    @strawberry.field(description="Numerical value of outer deviation in pixels")
    def margin_outer_deviation(self) -> int:
        return self.get('margin_outer_deviation')

    @strawberry.field(description="Numerical value of inner deviation in pixels")
    def margin_inner_deviation(self) -> int:
        return self.get('margin_inner_deviation')

    @strawberry.field(description="Boolean value that indicates presence/absence of noise in the image")
    def is_not_noisy(self) -> bool:
        return self.get('is_not_noisy')

    @strawberry.field(description="Numerical value that represents the score of image noise in points from 0 to 100")
    def noise_score(self) -> int:
        return self.get('noise_score')

    @strawberry.field(description="Numerical value of confidence that the image"
                                  " contains a watermark in points from 0 to 100")
    def watermark_score(self) -> int:
        return self.get('watermark_score')

    @strawberry.field(description="Boolean value for presence/absence of watermark in the image")
    def has_watermark(self) -> bool:
        return self.get('has_watermark')

    @strawberry.field(description="Numerical value that represents the score of"
                                  " dynamic range of intensity in points from 0 to 100")
    def dynamic_range_score(self) -> int:
        return self.get('dynamic_range_score')

    @strawberry.field(description="Boolean value that represents that the dynamic range"
                                  " of image intensity in the face area exceeds/doesn’t exceed the value of 128")
    def is_dynamic_range_acceptable(self) -> bool:
        return self.get('is_dynamic_range_acceptable')

    @strawberry.field(description="Boolean value for background uniformity")
    def is_background_uniform(self) -> bool:
        return self.get('is_background_uniform')

    @strawberry.field(description="Numerical value for background uniformity score in points from 0 to 100")
    def background_uniformity_score(self) -> int:
        return self.get('background_uniformity_score')


@strawberry.type(description="Information about face quality")
class Quality:
    @strawberry.field(description="Contains the data of the Quality Assessment Algorithm operation")
    def qaa(self) -> Qaa:
        return self.get('qaa')


@strawberry.type(description="Information on face detection and processing")
class FaceProcessInfo:
    @strawberry.field(description="Face identification number. Each face has a unique id within the list")
    def id(self) -> int:
        return self.get('id')

    @strawberry.field(name="class", description="Object type. The object for current API always has a face type")
    def class_(self) -> str:
        return self.get('class')

    @strawberry.field(description="Face detection confidence")
    def confidence(self) -> float:
        return self.get('confidence')

    @strawberry.field(
        description="Bounding Box. The rectangle that represents face bounds in the image."
                    " The bounds are calculated relative to the coordinates of the original image."
                    " The first two bbox coordinates are X and Y of the left top point,"
                    " the second two are X and Y of the right bottom point"
    )
    def bbox(self) -> List[float]:
        return self.get('bbox')

    @strawberry.field(description="Anthropometric points")
    def fitter(self) -> Fitter:
        return self.get('fitter')

    @strawberry.field(description="Estimation of emotions from face image")
    def emotions(self) -> List[Emotions]:
        return self.get('emotions')

    @strawberry.field(description="Face mask presence")
    def mask(self) -> MaskConfidenceValue:
        return self.get('mask')

    @strawberry.field(description="Biometric template coded in base64 used for face comparison")
    def templates(self) -> Templates:
        return self.get('templates')

    @strawberry.field(description="Gender estimation from face image")
    def gender(self) -> str:
        return self.get('gender')

    @strawberry.field(description="Age estimation from face image")
    def age(self) -> int:
        return self.get('age')

    @strawberry.field(description="Head rotation angles")
    def angles(self) -> Angles:
        return self.get('angles')

    @strawberry.field(description="Estimation that a person in the image is real or fake")
    def liveness(self) -> LivenessConfidenceValue:
        return self.get('liveness')

    @strawberry.field(description="Information about  image quality")
    def quality(self) -> Quality:
        return self.get('quality')


@strawberry.type(description="Result of image processing")
class ImageProcessInfo:
    @strawberry.field(description="Image in base64 format")
    def image(self) -> str:
        return self.get('$image')

    @strawberry.field(description="Result of face detection and processing")
    def faces(self) -> List[FaceProcessInfo]:
        return self.get('objects')

    @strawberry.field(description="Result of image processing in sample format")
    def sample(self) -> JSON:
        return self
