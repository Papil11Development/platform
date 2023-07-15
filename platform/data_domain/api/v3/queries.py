import strawberry
from strawberry.types import Info
from data_domain.api.v3.types import ImageProcessInfo
from data_domain.managers import SampleEnricher
from platform_lib.strawberry_auth.permissions import IsHaveAccess, IsWorkspaceActive
from platform_lib.types import CustomBinaryType


@strawberry.type
class Query:

    @strawberry.field(permission_classes=[IsHaveAccess, IsWorkspaceActive],
                      description="Detect and process faces on the image")
    def process_image(self, info: Info, image: CustomBinaryType) -> ImageProcessInfo:
        faces_selection = next(filter(lambda x: x.name == 'faces', info.selected_fields[0].selections))
        requested_fields = [field.name for field in faces_selection.selections]

        data = SampleEnricher(image=image)
        functions = SampleEnricher.get_functions_by_fields(requested_fields)

        for function in functions:
            function(data)

        return data.get_result()  # noqa
