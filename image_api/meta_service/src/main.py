import importlib
import logging
from functools import partial
from typing import Optional

from opentelemetry.trace import Status, StatusCode
from plib.tracing import set_tracing_flag, ConnectionManager

from settings import (APP_ROOT_PATH,
                      BLOCK_CONFIG,
                      FACE_SDK_CONF_DIR_PATH,
                      FACE_SDK_DLL_PATH,
                      MAX_BODY_SIZE,
                      PROCESSING_DEPENDENCIES,
                      GRPC_SERVICE_URL,
                      UNIT_TYPE,
                      GRPC_ACCESS_TOKEN,
                      GRPC_BLOCKS,
                      GRPC_QUALITY_BLOCKS,
                      CONVERSION_NEEDLE,
                      VERSION_CONFIG,
                      TRACING_ENABLED,
                      TRACER_URL,
                      SERVICE_NAME)

from fastapi.staticfiles import StaticFiles
from api.description import get_app_description

from api.sdk import ProcessingBlock, ProcessingBlockFactory
from api.sdk.errors import SDKException

from api.utils import sample_b64_resolver, sample_binary_resolver, sample_binary_resolver_v2
from errors import RequestException

from fastapi import FastAPI, File, HTTPException, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse

from plib.tracing.utils import ContextStub, get_top_context_from_request

processing_block: Optional[ProcessingBlock] = None

swagger_ui_parameters = {
    "syntaxHighlight.theme": "obsidian",
    "defaultModelsExpandDepth": -1,
}

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    root_path=APP_ROOT_PATH,
    swagger_ui_parameters=swagger_ui_parameters,
    **get_app_description()
)

app.mount("/static", StaticFiles(directory="static"), name="static")

set_tracing_flag(bool(TRACING_ENABLED))
tracer = ConnectionManager.init_connection(SERVICE_NAME, TRACER_URL)


@app.middleware("http")
async def check_content_length(request: Request, call_next):
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > MAX_BODY_SIZE:
        return JSONResponse(status_code=400, content={'detail': 'Request body size is too large'})
    response = await call_next(request)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={'detail': exc.detail},
    )


@app.on_event("startup")
async def startup_event():
    global processing_block

    if UNIT_TYPE in GRPC_BLOCKS:
        processing_block = ProcessingBlockFactory().create_grpc_block(
            GRPC_SERVICE_URL, BLOCK_CONFIG, CONVERSION_NEEDLE, GRPC_ACCESS_TOKEN
        )
    elif UNIT_TYPE in GRPC_QUALITY_BLOCKS:
        processing_block = ProcessingBlockFactory().create_grpc_face_sdk_block(
            FACE_SDK_DLL_PATH, FACE_SDK_CONF_DIR_PATH,
            GRPC_SERVICE_URL, BLOCK_CONFIG, CONVERSION_NEEDLE, GRPC_ACCESS_TOKEN
        )
    else:
        processing_block = ProcessingBlockFactory().create_face_sdk_block(
            FACE_SDK_DLL_PATH, FACE_SDK_CONF_DIR_PATH, BLOCK_CONFIG, CONVERSION_NEEDLE
        )


@app.on_event("shutdown")
async def shutdown_event():
    global processing_block
    del processing_block


def convert_sample_to_v1_output(sample: dict):
    if 'image' in sample:
        sample['image'] = sample['image']['blob']

    objs = sample.get('objects')
    if objs:
        for o in objs:
            if "template" in o and isinstance(o['template'], dict):
                o["template"] = o["template"]['blob']


def convert_sample_v1_to_input(sample: dict):
    if "$image" in sample:
        sample["$image"] = {
            "blob": sample["$image"],
            "format": "IMAGE"
        }
    objs = sample.get('objects')
    if objs:
        for o in objs:
            if "$template" in o:
                o["$template"] = {
                    "blob": o["$template"],
                    "format": "NDARRAY"
                }


for version, params in VERSION_CONFIG.items():
    module = importlib.import_module(f"api.types.{version}.pydantic")
    Sample = module.Sample
    SampleInput = module.SampleInput


    def web_sample_processor(sample_input: dict, api_version: str, resp_sample):
        global processing_block
        if api_version == 'v1':
            convert_sample_v1_to_input(sample_input)
        bsm_char = {"v1": "$", "v2": "_"}[api_version]
        sample_b64_resolver(sample_input, bsm_char)
        n_sample = processing_block.process(sample_input, api_version)
        if api_version == 'v1':
            convert_sample_to_v1_output(n_sample)
            sample_binary_resolver(n_sample)
        else:
            sample_binary_resolver_v2(n_sample)
        return resp_sample(**n_sample)


    async def process_sample(resp_sample,
                             api_version,
                             request: Request,
                             sample_input: SampleInput):
        ctx = get_top_context_from_request(request)
        with tracer.start_as_current_span("process_sample", context=ctx) if tracer else ContextStub() as span:
            try:
                return web_sample_processor(sample_input.dict(by_alias=True), api_version, resp_sample)
            except (RequestException, SDKException) as ex:
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(ex)
                raise HTTPException(status_code=400, detail=str(ex))


    partial_func = partial(process_sample, Sample, version)
    partial_func.__doc__ = process_sample.__doc__
    if version == 'v1':
        app.post("/process/sample", response_model=Sample, tags=[version])(partial_func)
    #     app.post("/v1/process/sample", response_model=Sample, tags=[version])(partial_func)
    # else:
    #     app.post(f"/{version}/process/sample", response_model=Sample, tags=[version])(partial_func)

    if not PROCESSING_DEPENDENCIES:
        async def process_image(resp_sample,
                                api_version, request: Request,
                                image: bytes = File(..., description="Image supplied to the input")):
            ctx = get_top_context_from_request(request)
            with tracer.start_as_current_span("process_image", context=ctx) if tracer else ContextStub() as span:
                try:
                    sample_input = {
                        "image": {
                            "blob": image,
                            "format": "IMAGE"
                        }
                    }
                    return web_sample_processor(sample_input, api_version, resp_sample)
                except (RequestException, SDKException) as ex:
                    raise HTTPException(status_code=400, detail=str(ex))


        partial_func = partial(process_image, Sample, version)
        partial_func.__doc__ = process_image.__doc__
        if version == 'v1':
            app.post("/process/image", response_model=Sample, tags=[version])(partial_func)
        #     app.post("/v1/process/image", response_model=Sample, tags=[version])(partial_func)
        # else:
        #     app.post(f"/{version}/process/image", response_model=Sample, tags=[version])(partial_func)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    print(f"{APP_ROOT_PATH}static/swagger-ui-bundle.js")
    return get_swagger_ui_html(
        swagger_ui_parameters=swagger_ui_parameters,
        openapi_url=f"{APP_ROOT_PATH}{app.openapi_url}",
        title=app.title + " - Swagger UI",
        swagger_js_url=f"{APP_ROOT_PATH}static/swagger-ui-bundle.js",
        swagger_css_url=f"{APP_ROOT_PATH}static/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=f"{APP_ROOT_PATH}{app.openapi_url}",
        title=app.title + " - ReDoc",
        redoc_js_url=f"{APP_ROOT_PATH}static/redoc.standalone.js",
    )
