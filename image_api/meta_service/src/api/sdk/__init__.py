from .errors import BlockInitialisationException
from .utils import ContextUtils
from .legacy_pb import LegacyProcessingBlock
import grpc


class ProcessingBlock:
    def __init__(self, processing_provider, config: dict, conversion_needle, access_data=None, grpc_service=None):
        self.processing_provider = processing_provider
        self.conversion_needle = conversion_needle
        try:
            self.block = processing_provider.create_processing_block(config)
        except Exception as e:
            # unknown unit type
            unknown_unit_type = (code_func := getattr(e, 'code', None)) is not None and code_func() == "0x18ba1f8e"

            block_not_face_sdk = isinstance(processing_provider, grpc.Channel)

            if unknown_unit_type or block_not_face_sdk:
                self.block = LegacyProcessingBlock(processing_provider, config, conversion_needle, access_data,
                                                   grpc_service=grpc_service)
            else:
                raise BlockInitialisationException(f"Failed to initialize processing block {e}")

    def process(self, sample_input: dict, version: str):
        io_data = {}
        for k, conversion_func in [
            ('image', lambda x: ContextUtils.image2bsm(x['blob'], self.conversion_needle)),
            ('objects', lambda x: x)
        ]:
            if k in sample_input and sample_input[k]:
                io_data[k] = conversion_func(sample_input[k])

        ContextUtils.prepare_context(io_data)

        if type(self.block) is LegacyProcessingBlock:
            self.block(io_data, version)
        else:
            objects = io_data.pop('objects', [])  # no processing if passing objects in fsdk 3.17
            self.block(io_data)
            ContextUtils.prepare_context(io_data)
            self.__merge_objects(objects, io_data['objects'])  # probable objects's mismatch
            io_data['objects'] = objects

        ContextUtils.clean_trash(io_data)

        if 'image' in sample_input:
            io_data['image'] = sample_input['image']
        return io_data

    @staticmethod
    def __merge_objects(objects, new_objects):
        for idx, n_o in enumerate(new_objects):
            if (idx + 1) > len(objects):
                objects.append({})
            objects[idx].update(n_o)

    def __del__(self):
        if isinstance(self.processing_provider, grpc.Channel):
            self.processing_provider.close()


class ProcessingBlockFactory:
    @staticmethod
    def create_face_sdk_block(fsdk_dll_path, fsdk_conf_dir_path, config: dict, conversion_needle: str):
        from face_sdk import FacerecService
        processing_provider = FacerecService.create_service(fsdk_dll_path, fsdk_conf_dir_path, '')

        return ProcessingBlock(processing_provider, config, conversion_needle)

    # TODO[QLC] crutch. remove create_grpc_face_sdk_block method after wrapper service appear
    @staticmethod
    def create_grpc_face_sdk_block(fsdk_dll_path, fsdk_conf_dir_path, grpc_url: str,
                                   config: dict, conversion_needle: str, access_token: str):
        from face_sdk import FacerecService
        processing_provider = FacerecService.create_service(fsdk_dll_path, fsdk_conf_dir_path, '')
        access_data = {'token': access_token}
        grpc_connection = grpc.insecure_channel(grpc_url)

        return ProcessingBlock(processing_provider, config, conversion_needle, access_data, grpc_connection)

    @staticmethod
    def create_grpc_block(grpc_url: str, config: dict, conversion_needle: str, access_token: str):
        access_data = {'token': access_token}
        processing_provider = grpc.insecure_channel(grpc_url)

        return ProcessingBlock(processing_provider, config, conversion_needle, access_data)
