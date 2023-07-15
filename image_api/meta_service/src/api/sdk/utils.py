import cv2
import numpy as np
import cv2


class ContextUtils:
    @classmethod
    def clean_trash(cls, ctx):
        for o in ctx.get('objects', []):
            if 'object@image' in o:
                del o['object@image']

    @classmethod
    def prepare_context(cls, ctx):
        objects = ctx.get('objects', [])
        if objects is None:
            objects = []

        for idx, o in list(enumerate(objects)):
            if not o:
                del objects[idx]

        for idx, o in list(enumerate(objects)):
            if 'id' not in o:
                o['id'] = idx

        ctx['objects'] = objects
        ctx['objects'].sort(key=lambda d: d['id'])  # TODO: maybe raise exception ?

    @classmethod
    def convert_color(cls, image_vector, color_model):
        if color_model == "RGB":
            image_vector = cv2.cvtColor(image_vector, cv2.COLOR_BGR2RGB)

        return image_vector

    @classmethod
    def image2bsm(cls, image: bytes, conversion_needle: str) -> dict:
        image_vector = cls.convert_color(
            cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR),
            conversion_needle
        )

        return {
            "blob": image_vector.tobytes(),
            "dtype": "uint8_t",
            "format": "NDARRAY",
            "shape": [dim for dim in image_vector.shape],
            "color_model": conversion_needle
        }

    @classmethod
    def bsm2image(cls, bsm: dict) -> bytes:
        image_vector = cls.convert_color(cls.bsm2array(bsm), bsm['color_model'])
        _, img = cv2.imencode('.png', image_vector)
        return img.tobytes()

    @classmethod
    def bsm2array(cls, bsm: dict) -> np.array:
        return np.frombuffer(bsm['blob'], np.uint8).reshape(bsm['shape'])

    @classmethod
    def array2bsm(cls, image_vector: np.array):
        return {
            "blob": image_vector.tobytes(),
            "dtype": "uint8_t",
            "format": "NDARRAY",
            "shape": [dim for dim in image_vector.shape]
        }
