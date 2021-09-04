import base64
from platform_lib.utils import get_collection

import strawberry
from django.conf import settings
from typing import Optional, List
from django.apps import apps
from strawberry import ID

from data_domain.api.v2.types import SampleOutput
from data_domain.managers import BlobMetaManager, SampleManager

from data_domain.api.v2.types import (PersonSearchResult as PersonSearchResult_v2,
                                      ProfileOutputData as ProfileOutputData_v2,
                                      SearchType as SearchType_v2)
from label_domain.api.v2.types import ProfileGroupOutput as ProfileGroupOutput_v2

profile_model = apps.get_model('person_domain', 'Profile')


@strawberry.type
class ProfileOutputDataLuna(ProfileOutputData_v2):
    @strawberry.field(description="Groups the profile belongs to")
    def profile_groups(self) -> Optional[List[ProfileGroupOutput_v2]]:
        return self.profile_groups.all()


@strawberry.type
class PersonSearchResultLuna(PersonSearchResult_v2):
    @strawberry.field
    def profile(root) -> Optional[ProfileOutputDataLuna]:
        return PersonSearchResult_v2.profile(root)   # noqa


@strawberry.type
class SearchTypeLuna(SearchType_v2):
    @strawberry.field
    def search_result(root) -> List[PersonSearchResultLuna]:
        return SearchType_v2.search_result(root)  # noqa


@strawberry.type(description="""
A Sample is an object that stores the image of a person's face and/or
a corresponding biometric template that is used for face recognition
""")
class SampleOutputLuna(SampleOutput):
    @strawberry.field(description="Vector of sample encoded in base64")
    def template(self) -> str:
        bm = BlobMetaManager(SampleManager.get_template_id(self.meta, settings.DEFAULT_TEMPLATES_VERSION))
        return base64.b64encode(bm.blob.data).decode()


SampleCollection = strawberry.type(
    get_collection(SampleOutputLuna, "SampleCollection"),
    description="Collection of samples"
)

sample_map = {'creationDate': 'creation_date', 'lastModified': 'last_modified'}
