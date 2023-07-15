import copy
import re
from io import BytesIO
import numpy as np
from grpc._channel import _InactiveRpcError
from plib.tracing.utils import ContextStub, get_tracer

from .errors import InvalidContextException, UnknownUnitType
from .utils import ContextUtils


class LegacyProcessingBlock:
    # TODO[QLC] crutch. remove grpc_service after wrapper service appear
    def __init__(self, service, config, conversion_needle, access_data=None, grpc_service=None):

        self.service = service
        self.access_data = access_data
        self.versions = config['versions']
        self.additional_variables = config.get('additional_variables')
        self.conversion_needle = conversion_needle
        self.enable_use_avx2 = config.get('use_avx2')
        self.downscale_rawsamples_to_preferred_size = config.get('downscale_rawsamples_to_preferred_size')
        raw_unit_type = config['unit_type']
        unit_type = config['unit_type'][1:]
        config['unit_type'] = unit_type
        self.enable_use_cuda = config.get('use_cuda')

        # TODO[QLC] crutch. remove sub_config after wrapper service appear
        self.sub_config = config.get('sub_block_config')

        self.config = config
        init_list = list()
        self.__block_implemenations = {}

        if unit_type != 'LIVENESS_ANTI_SPOOFING':
            init_list.append('fsdk_deps')
        if unit_type == 'FACE_DETECTOR_LIVENESS_ESTIMATOR':
            init_list += ['capturer', 'liveness']
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self,
                                                               f"face_detector_liveness_estimator_block_{version}")
        elif unit_type == 'FACE_DETECTOR_FACE_FITTER':
            init_list.append('capturer')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"face_detector_fitter_block_{version}")
        elif unit_type == 'QUALITY_ASSESSMENT_ESTIMATOR':
            init_list.append('block')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"quality_assessment_estimator_block_{version}")
        elif unit_type == 'FACE_DETECTOR_TEMPLATE_EXTRACTOR':
            init_list += ['capturer', 'recognizer-processing']
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self,
                                                               f"face_detector_template_extractor_block_{version}")
        elif unit_type == 'VERIFY_MATCHER':
            init_list.append('recognizer-matching')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"verify_matcher_block_{version}")
        elif unit_type == 'SEARCH_MATCHER':
            init_list.append('recognizer-matching')
            for version in self.versions:
                self.__block_implemenations[version] = self.search_matcher_block
        elif unit_type == 'LIVENESS_ANTI_SPOOFING':
            init_list.append('grpc')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"liveness_anti_spoofing_block_{version}")
        # TODO[QLC] crutch. remove QUALITY_LIVENESS_ANTI_SPOOFING after wrapper service appear
        elif unit_type == 'QUALITY_LIVENESS_ANTI_SPOOFING':
            init_list += ['grpc', 'block', 'capturer']
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"quality_liveness_anti_spoofing_block_{version}")
        elif unit_type == 'GENDER_ESTIMATOR':
            init_list.append('block')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"gender_estimator_block_{version}")
        elif unit_type == 'EMOTION_ESTIMATOR':
            init_list.append('block')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"emotion_estimator_block_{version}")
        elif unit_type == 'MASK_ESTIMATOR':
            init_list.append('block')
            for version in self.versions:
                self.__block_implemenations[version] = getattr(self, f"mask_estimator_block_{version}")
        elif unit_type in ['AGE_ESTIMATOR']:
            init_list.append('block')
            for version in self.versions:
                self.__block_implemenations[version] = self.generic_estimator_base
        else:
            raise UnknownUnitType(f"Unknown unit type {raw_unit_type}")

        for el in init_list:
            if el == 'fsdk_deps':
                from face_sdk.modules import recognizer as facesdk_recognizer
                from face_sdk.modules.liveness_2d_estimator import Liveness
                from face_sdk import Config, Error

                # Get face sdk libs if legacy block is sdk dependency
                self.facesdk_recognizer = facesdk_recognizer
                self.Liveness = Liveness
                self.Config = Config
                self.Error = Error

            if el == 'liveness':
                self.__liveness_estimator = self.service.create_liveness_2d_estimator(config['liveness_config'])
            elif el == 'recognizer-processing':
                self.__recognizer = self.service.create_recognizer(
                    self.__resolve_config(
                        config['recognizer_config'], use_avx2=self.enable_use_avx2,
                        use_cuda=self.enable_use_cuda
                    ), matching=False, processing=True
                )
            elif el == 'recognizer-matching':
                self.__recognizer = self.service.create_recognizer(
                    self.__resolve_config(
                        config['recognizer_config'], use_avx2=self.enable_use_avx2,
                        use_cuda=self.enable_use_cuda
                    ), matching=True, processing=False
                )
            elif el == 'capturer':
                self.__capturer = self.service.create_capturer(
                    self.__resolve_config(
                        config['capturer_config'],
                        use_cuda=self.enable_use_cuda,
                        downscale_rawsamples_to_preferred_size=self.downscale_rawsamples_to_preferred_size
                    )
                )
            elif el == 'block':
                self.__init_block()
            elif el == 'grpc':
                from service_pb2_grpc import AntispoofingStub  # noqa
                import service_pb2  # noqa

                self.stub = AntispoofingStub(grpc_service or self.service)
                self.types = service_pb2

    def __init_block(self):
        # TODO[QLC] crutch. remove self.sub_config after wrapper service appear
        self.__block = self.service.create_processing_block(self.sub_config or self.config)

    def __resolve_config(self, config, **kwargs):
        cfg = self.Config(config)
        for k, v in kwargs.items():
            cfg.override_parameter(k, kwargs[k])
        return cfg

    def __call__(self, ctx, version):
        self.__block_implemenations[version](ctx)

    def __process_object(self, img_ctx, obj_ctx):
        ctx = {"image_ptr": img_ctx, **obj_ctx}
        self.block(ctx)
        del ctx["image_ptr"]
        return ctx

    def block(self, ctx):
        try:
            return self.__block(ctx)
        except self.Error as er:
            self.__init_block()
            raise er

    @staticmethod
    def __get_detect(id, _class, cap_obj, img_shape) -> dict:
        bbx = cap_obj.get_rectangle()
        return {
            "id": id,
            "class": _class,
            "bbox": [
                float(bbx.x / img_shape[1]),
                float(bbx.y / img_shape[0]),
                float((bbx.x + bbx.width) / img_shape[1]),
                float((bbx.y + bbx.height) / img_shape[0]),
            ],
            "confidence": cap_obj.get_score()
        }

    def face_detector_fitter_block_v1(self, ctx):
        tracer = get_tracer(__name__)

        ctx_objects = ctx['objects']

        with tracer.start_as_current_span("fitter_capture_v1") if tracer else ContextStub() as span:
            cap_objects = self.__capturer.capture(ContextUtils.bsm2image(ctx['image']))

        for idx, cap_obj in enumerate(cap_objects):
            if (idx + 1) > len(ctx_objects):  # TODO use merge_objects function in ContextUtils
                ctx_objects.append({})

            ctx_objects[idx].update({
                **self.__get_detect(idx, 'face', cap_obj, ctx['image']['shape']),
                "fitter": {
                    "keypoints": [point for pt in cap_obj.get_landmarks() for point in [pt.x, pt.y, pt.z]],
                    "fitter_type": "fda",
                    "left_eye": [cap_obj.get_left_eye().x, cap_obj.get_left_eye().y],
                    "right_eye": [cap_obj.get_right_eye().x, cap_obj.get_right_eye().y]
                },
                "angles": {
                    "yaw": cap_obj.get_angles().yaw,
                    "pitch": cap_obj.get_angles().pitch,
                    "roll": cap_obj.get_angles().roll
                }
            })

    def face_detector_fitter_block_v2(self, ctx):
        tracer = get_tracer(__name__)

        ctx_objects = ctx['objects']

        with tracer.start_as_current_span("fitter_capture_v2") if tracer else ContextStub() as span:
            cap_objects = self.__capturer.capture(ContextUtils.bsm2image(ctx['image']))

        for idx, cap_obj in enumerate(cap_objects):
            if (idx + 1) > len(ctx_objects):  # TODO use merge_objects function in ContextUtils
                ctx_objects.append({})
            point_names = ["left_eye_brow_left", "left_eye_brow_up", "left_eye_brow_right", "right_eye_brow_left",
                           "right_eye_brow_up", "right_eye_brow_right", "left_eye_left", "left_eye", "left_eye_right",
                           "right_eye_left", "right_eye", "right_eye_right", "left_ear_bottom", "nose_left", "nose",
                           "nose_right", "right_ear_bottom", "mouth_left", "mouth", "mouth_right", "chin", ]
            keypoints = cap_obj.get_landmarks()
            ctx_objects[idx].update({
                **self.__get_detect(idx, 'face', cap_obj, ctx['image']['shape']),
                "keypoints": {name: {"proj": [keypoints[i].x, keypoints[i].y]} for i, name in
                              enumerate(point_names)},
                "pose": {
                    "yaw": cap_obj.get_angles().yaw,
                    "pitch": cap_obj.get_angles().pitch,
                    "roll": cap_obj.get_angles().roll
                }
            })

    def face_detector_liveness_estimator_base(self, ctx, result_mapping: dict):
        tracer = get_tracer(__name__)

        ctx_objects = ctx['objects']

        with tracer.start_as_current_span("liveness_capture") if tracer else ContextStub() as span:
            cap_objects = self.__capturer.capture(ContextUtils.bsm2image(ctx['image']))

        for idx, cap_obj in enumerate(cap_objects):
            if (idx + 1) > len(ctx_objects):  # TODO use merge_objects function in ContextUtils
                ctx_objects.append({})

            with tracer.start_as_current_span("liveness_estimate") if tracer else ContextStub() as span:
                le_res = self.__liveness_estimator.estimate(cap_obj)

            ctx_objects[idx].update({
                **self.__get_detect(idx, 'face', cap_obj, ctx['image']['shape']),
                "liveness": {
                    "value": result_mapping[le_res.liveness],
                    "confidence": le_res.score
                }})
        return ctx

    def quality_assessment_base(self, ctx):
        tracer = get_tracer(__name__)

        objects = []
        if not ctx['objects']:
            raise InvalidContextException('No object were passed')
        for o in ctx['objects']:
            with tracer.start_as_current_span("quality_block") if tracer else ContextStub() as span:
                objects.append(self.__process_object(ctx['image'], o) if o.get('class') == 'face' else o)

        return objects

    def face_detector_template_extractor_block_v1(self, ctx):
        tracer = get_tracer(__name__)

        ctx_objects = ctx['objects']

        with tracer.start_as_current_span("template_capture_v1") if tracer else ContextStub() as span:
            cap_objects = self.__capturer.capture(ContextUtils.bsm2image(ctx['image']))

        for idx, cap_obj in enumerate(cap_objects):
            if (idx + 1) > len(ctx_objects):  # TODO use merge_objects function in ContextUtils
                ctx_objects.append({})

            with tracer.start_as_current_span("template_extract_v1") if tracer else ContextStub() as span:
                template = self.__recognizer.processing(cap_obj)

            with BytesIO() as buffer:
                template.save(buffer)
                buffer.seek(0)
                bin_template = buffer.read()
                template_vector = np.frombuffer(bin_template, np.float32)
                ctx_objects[idx].update({
                    **self.__get_detect(idx, 'face', cap_obj, ctx['image']['shape']),
                    "template": bin_template,
                    "template_size": template_vector.size
                })
        return ctx

    def face_detector_template_extractor_block_v2(self, ctx):
        tracer = get_tracer(__name__)

        # "method12v1000_recognizer.xml"
        version, weight = self.config['recognizer_config'] \
            .replace('method', '') \
            .replace('_recognizer.xml', '') \
            .split('v')
        ctx_objects = ctx['objects']

        with tracer.start_as_current_span("template_capture_v2") if tracer else ContextStub() as span:
            cap_objects = self.__capturer.capture(ContextUtils.bsm2image(ctx['image']))

        for idx, cap_obj in enumerate(cap_objects):
            if (idx + 1) > len(ctx_objects):  # TODO use merge_objects function in ContextUtils
                ctx_objects.append({})

            with tracer.start_as_current_span("template_extract_v2") if tracer else ContextStub() as span:
                template = self.__recognizer.processing(cap_obj)

            with BytesIO() as buffer:
                template.save(buffer)
                buffer.seek(0)
                bin_template = buffer.read()
                template_vector = np.frombuffer(bin_template, np.float32)
                ctx_objects[idx].update({
                    **self.__get_detect(idx, 'face', cap_obj, ctx['image']['shape']),
                    "template": {
                        f"face_template_extractor_{weight}_{version}": {
                            "blob": bin_template,
                            "format": "NDARRAY",
                            "dtype": "uint8_t",
                            "shape": [dim for dim in template_vector.shape],
                        }
                    }
                })
        return ctx

    def verify_matcher_block_v1(self, ctx):
        tracer = get_tracer(__name__)

        ctx_objects = ctx['objects']
        templates = []
        for obj in ctx_objects[:2]:
            if obj.get('class') == 'face':
                templates.append(self.__recognizer.load_template(BytesIO(obj['template']['blob'])))

        with tracer.start_as_current_span("verify_match_v1") if tracer else ContextStub() as span:
            result = self.__recognizer.verify_match(*templates)

        ctx.update({
            "verification": {
                "distance": result.distance,
                "fa_r": result.fa_r,
                "fr_r": result.fr_r,
                "score": result.score
            }
        })

        return ctx

    def verify_matcher_block_v2(self, ctx):
        tracer = get_tracer(__name__)

        version, weight = self.config['recognizer_config'] \
            .replace('method', '') \
            .replace('_recognizer.xml', '') \
            .split('v')

        ctx_objects = ctx['objects']
        templates = []
        for obj in ctx_objects[:2]:
            if obj.get('class') == 'face':
                templates.append(
                    self.__recognizer.load_template(
                        BytesIO(obj['template'][f"face_template_extractor_{weight}_{version}"]['blob'])
                    )
                )

        with tracer.start_as_current_span("verify_match_v2") if tracer else ContextStub() as span:
            result = self.__recognizer.verify_match(*templates)

        ctx.update({
            "verification": {
                "distance": result.distance,
                "fa_r": result.fa_r,
                "fr_r": result.fr_r,
                "score": result.score
            }
        })

        return ctx

    def generic_estimator_base(self, ctx):
        tracer = get_tracer(__name__)

        objects = ctx.pop('objects', [])
        if objects:
            image_vector = ContextUtils.bsm2array(ctx['image'])
            height, width = image_vector.shape[:2]
            n_objects = []
            for idx, obj in enumerate(objects):
                if obj.get('class') == 'face':
                    x1, y1, x2, y2 = [(0 if el < 0 else el if el < 1 else 1) for el in obj['bbox']]
                    img_vector_crop = image_vector[int(y1 * height):int(y2 * height), int(x1 * width):int(x2 * width)]
                    n_ctx = {"image": ContextUtils.array2bsm(img_vector_crop)}

                    with tracer.start_as_current_span("generic_block") if tracer else ContextStub() as span:
                        self.block(n_ctx)

                    generic_estimation_object = n_ctx['objects'][0]
                    obj = {**obj, **generic_estimation_object}

                n_objects.append(obj)
        else:
            with tracer.start_as_current_span("generic_block") if tracer else ContextStub() as span:
                self.block(ctx)
            n_objects = ctx.get('objects', [])

        ctx['objects'] = n_objects
        return ctx

    def search_matcher_block(self, ctx):
        ctx_objects = ctx['objects']
        templates = []
        for obj in ctx_objects:
            if obj.get('class') == 'face':
                templates.append(self.__recognizer.load_template(BytesIO(obj['template']['blob'])))

        matches = []
        unique_accord = []
        for i in range(len(ctx_objects)):
            for j in range(len(ctx_objects)):
                s1_id, templates_1 = ctx_objects[i]['id'], [templates[i]]
                s2_id, templates_2 = ctx_objects[j]['id'], [templates[j]]

                if i == j or not len(templates_1) or not len(templates_2):
                    continue

                template_index = self.__recognizer.create_index(templates_2, 1)
                query_k_nearest = len(templates_2)

                list_search_results = []
                for query_template in templates_1:
                    search_results = self.__recognizer.search(
                        [query_template],
                        template_index,
                        query_k_nearest,
                        self.facesdk_recognizer.SearchAccelerationType.NO_SEARCH_ACCELERATION)
                    list_search_results.append(search_results[0])

                for q, search_results in enumerate(list_search_results):
                    obj1_id = ctx_objects[q]['id']
                    for search_result in search_results:
                        obj2_id = ctx_objects[int(search_result.i)]['id']
                        accord = [f"{s1_id}@{obj1_id}", f"{s2_id}@{obj2_id}"]

                        if set(accord) in unique_accord:
                            continue

                        is_similar = search_result.match_result.score >= 0.9

                        matches.append({
                            "accord": accord,
                            "confidence": search_result.match_result.score if is_similar
                            else 1 - search_result.match_result.score,
                            "is_similar": is_similar,
                        })
                        unique_accord.append(set(accord))

        ctx.update({
            "matches": matches
        })

        return ctx

    def liveness_anti_spoofing_base(self, ctx, result_mapping: dict):
        tracer = get_tracer(__name__)

        ctx_objects = ctx['objects']

        png_image = ContextUtils.bsm2image(ctx['image'])

        request = self.types.AntispoofingRequest(data=BytesIO(png_image))

        try:
            with tracer.start_as_current_span("antispoofing_request") if tracer else ContextStub() as span:
                response, call = self.stub.Execute.with_call(
                    request=request,
                    # only lowercase in metadata
                    metadata=(("authorization", f"Bearer {self.access_data['token']}"),)
                )

            liveness = {'confidence': 1 - response.confidence, 'value': result_mapping[response.isReal]}
        except _InactiveRpcError as ex:
            # mask grpc error
            if ex.details() == "Received message exceeds the maximum configured message size.":
                raise InvalidContextException("Request body size is too large")
            else:
                raise ex

        if ctx_objects:
            for ctx_object in ctx_objects:
                ctx_object['liveness'] = liveness
        else:
            ctx_objects.append({'id': 0, 'class': 'face', 'liveness': liveness})
        return ctx

    # TODO crutch remove after wrapper service appear
    def quality_liveness_anti_spoofing_base(self, ctx, result_mapping: dict):
        tracer = get_tracer(__name__)

        img_shape = ctx['image']['shape']
        ctx_objects = ctx['objects']
        obj_copy = copy.deepcopy(ctx_objects)

        face_object_offset = 0

        # calculate face object offset if body object already persist in context
        for ctx_object in ctx_objects:
            if (obj_class := ctx_object.get('class')) is not None and obj_class != 'face':
                face_object_offset += 1

        png_image = ContextUtils.bsm2image(ctx['image'])

        with tracer.start_as_current_span("quality_antispoofing_capture") if tracer else ContextStub() as span:
            capture_obj = self.__capturer.capture(png_image)

        if len(capture_obj) > 1 and self.additional_variables['reject_many_faces']:
            raise InvalidContextException('More than one face detected')

        for idx, cap_obj in enumerate(capture_obj):
            if (idx + face_object_offset + 1) > len(obj_copy):
                obj_copy.append({})

            obj_copy[idx + face_object_offset].update({
                **self.__get_detect(idx, 'face', cap_obj, img_shape),
                "fitter": {
                    "keypoints": [point for pt in cap_obj.get_landmarks() for point in [pt.x, pt.y, pt.z]],
                    "fitter_type": "fda",
                    "left_eye": [cap_obj.get_left_eye().x, cap_obj.get_left_eye().y],
                    "right_eye": [cap_obj.get_right_eye().x, cap_obj.get_right_eye().y]
                },
                "angles": {
                    "yaw": cap_obj.get_angles().yaw,
                    "pitch": cap_obj.get_angles().pitch,
                    "roll": cap_obj.get_angles().roll
                }
            })

        if len(capture_obj) == 1:
            with tracer.start_as_current_span("quality_antispoofing_estimate") if tracer else ContextStub() as span:
                total_score = self.__process_object(
                    ctx['image'],
                    obj_copy[face_object_offset]
                )['quality']['qaa']['totalScore']

            threshold = self.additional_variables['quality_threshold']

            if total_score < threshold:
                raise InvalidContextException(
                    f'Low image quality. Calculated score value ({total_score})'
                    f' is less than the threshold ({threshold})'
                )

            request = self.types.AntispoofingRequest(data=BytesIO(png_image))

            try:
                with tracer.start_as_current_span("quality_antispoofing_request") if tracer else ContextStub() as span:
                    response, call = self.stub.Execute.with_call(
                        request=request,
                        # only lowercase in metadata
                        metadata=(("authorization", f"Bearer {self.access_data['token']}"),)
                    )
            except _InactiveRpcError as ex:
                # mask grpc error
                if ex.details() == "Received message exceeds the maximum configured message size.":
                    raise InvalidContextException("Request body size is too large")
                else:
                    raise ex

            if (face_object_offset + 1) > len(ctx_objects):
                ctx_objects.append({})

            ctx_objects[face_object_offset].update({
                'id': face_object_offset,
                'class': 'face',
                'liveness': {
                    'confidence': 1 - response.confidence,
                    'value': result_mapping[response.isReal]}
            })

        return ctx

    def gender_estimator_block_v1(self, ctx):
        return self.generic_estimator_base(ctx)

    def gender_estimator_block_v2(self, ctx):
        ctx = self.generic_estimator_base(ctx)

        for ctx_object in ctx["objects"]:
            ctx_object['gender'] = ctx_object['gender'].lower()

        return ctx

    def emotion_estimator_block_v1(self, ctx):
        return self.generic_estimator_base(ctx)

    def emotion_estimator_block_v2(self, ctx):
        ctx = self.generic_estimator_base(ctx)

        for ctx_object in ctx["objects"]:
            list(map(lambda x: x.__setitem__('emotion', x['emotion'].lower()), ctx_object['emotions']))

        return ctx

    def mask_estimator_block_v1(self, ctx):
        return self.generic_estimator_base(ctx)

    def mask_estimator_block_v2(self, ctx):
        ctx = self.generic_estimator_base(ctx)

        for ctx_object in ctx["objects"]:
            ctx_object['has_medical_mask'] = ctx_object.pop('mask')

        return ctx

    def quality_assessment_estimator_block_v1(self, ctx):
        ctx['objects'] = self.quality_assessment_base(ctx)
        return ctx

    def quality_assessment_estimator_block_v2(self, ctx):
        def camel_to_snake(string: str):
            return re.sub(r'(?<!^)(?=[A-Z])', '_', string).lower()

        for ctx_object in ctx['objects']:
            keypoints = ctx_object['keypoints']
            kp_ar = []
            for keypoint in keypoints.values():
                proj = keypoint['proj'] + [0]
                kp_ar += proj
            ctx_object['fitter'] = {
                'keypoints': kp_ar,
                "fitter_type": "fda",
                "left_eye": keypoints['left_eye']['proj'],
                "right_eye": keypoints['right_eye']['proj']
            }
            ctx_object['angles'] = ctx_object.pop('pose')

        objects = self.quality_assessment_base(ctx)
        for ctx_object in objects:
            quality = ctx_object['quality'].pop('qaa')

            for key, value in quality.items():
                ctx_object['quality'][camel_to_snake(key)] = value
            ctx_object['pose'] = ctx_object.pop('angles')
            ctx_object.pop('fitter')

        ctx['objects'] = objects
        return ctx

    def face_detector_liveness_estimator_block_v1(self, ctx):
        result_mapping = {
            self.Liveness.NOT_ENOUGH_DATA: 'NOT_ENOUGH_DATA',
            self.Liveness.REAL: 'REAL',
            self.Liveness.FAKE: 'FAKE'
        }
        return self.face_detector_liveness_estimator_base(ctx, result_mapping)

    def face_detector_liveness_estimator_block_v2(self, ctx):
        result_mapping = {
            self.Liveness.NOT_ENOUGH_DATA: 'not_enough_data',
            self.Liveness.REAL: 'real',
            self.Liveness.FAKE: 'fake'
        }
        return self.face_detector_liveness_estimator_base(ctx, result_mapping)

    def liveness_anti_spoofing_block_v1(self, ctx):
        result_mapping = {
            True: 'REAL',
            False: 'FAKE'
        }
        return self.liveness_anti_spoofing_base(ctx, result_mapping)

    def liveness_anti_spoofing_block_v2(self, ctx):
        result_mapping = {
            True: 'real',
            False: 'fake'
        }
        return self.liveness_anti_spoofing_base(ctx, result_mapping)

    def quality_liveness_anti_spoofing_block_v1(self, ctx):
        result_mapping = {
            True: 'REAL',
            False: 'FAKE'
        }
        return self.quality_liveness_anti_spoofing_base(ctx, result_mapping)

    def quality_liveness_anti_spoofing_block_v2(self, ctx):
        result_mapping = {
            True: 'real',
            False: 'fake'
        }
        return self.quality_liveness_anti_spoofing_base(ctx, result_mapping)
