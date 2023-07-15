import base64

from data_domain.managers import SampleManager
from data_domain.models import Sample, BlobMeta
from platform_lib.exceptions import BadInputDataException
from platform_lib.utils import SampleObjectsName, validate_image


def check_search_input_data(**kwargs) -> bool:
    source_sample_ids = kwargs.get("source_sample_ids")
    source_sample_data = kwargs.get("source_sample_data")
    source_image = kwargs.get("source_image")
    confidence_threshold = kwargs.get("confidence_threshold")
    max_num_of_candidates_returned = kwargs.get("max_num_of_candidates_returned")

    if sum(map(bool, [source_sample_ids, source_sample_data, source_image])) != 1:
        raise BadInputDataException("0x963fb254")

    if confidence_threshold < 0 or confidence_threshold > 1:
        raise BadInputDataException("0xf47f116a")

    if max_num_of_candidates_returned < 1 or max_num_of_candidates_returned > 100:
        raise BadInputDataException("0xf8be6762")

    return True


def get_templates(template_version, source_sample_ids, source_sample_data, source_image) -> list:
    objects_key = f'objects@{SampleObjectsName.PROCESSING_CAPTURER}'

    if source_sample_ids:
        samples = sorted(Sample.objects.filter(id__in=source_sample_ids),
                         key=lambda x: source_sample_ids.index(str(x.id)))
        template_ids = [SampleManager.get_template_id(sample.meta, template_version) for sample in samples]
        templates_meta = sorted(BlobMeta.objects.select_related('blob').filter(id__in=template_ids),
                                key=lambda x: template_ids.index(str(x.id)))
        templates = [base64.standard_b64encode(template_meta.blob.data.tobytes()).decode() for
                     template_meta in templates_meta]

    elif source_sample_data:
        source_sample_data = source_sample_data.get('data') or source_sample_data  # if input with data or not
        source_templates = [face['templates'][f"${template_version}"] for
                            face in source_sample_data[objects_key]]
        try:
            template_ids = [template.get('id') for template in source_templates]
            templates_meta = sorted(BlobMeta.objects.select_related('blob').filter(id__in=template_ids),
                                    key=lambda x: template_ids.index(str(x.id)))
            templates = [base64.standard_b64encode(template_meta.tobytes()).decode()
                         for template_meta in templates_meta]
        except AttributeError:
            templates = source_templates

    else:
        validate_image(source_image)
        processing_result = SampleManager.process_image(image=source_image, template_version=template_version)
        templates = [face['templates'][f"${template_version}"] for face in processing_result[objects_key]]

    return templates
