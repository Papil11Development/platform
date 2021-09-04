import strawberry
from typing import Optional, List
from data_domain.api.vLuna.types import SampleOutputLuna as SampleOutput
from person_domain.api.v2.types import ProfileOutput as ProfileOutput_v2
from platform_lib.utils import get_collection


@strawberry.type(description="Object that represents a person and contains all the information about that person")
class ProfileOutput(ProfileOutput_v2):
    @strawberry.field(description="Objects that stored info about human photos.")
    def samples(self) -> Optional[List[SampleOutput]]:
        return ProfileOutput_v2.samples(self)

    @strawberry.field(description="Best human photo")
    def main_sample(self) -> Optional[SampleOutput]:
        return self.samples.filter(id=self.info.get("main_sample_id")).first()


ProfilesCollection = strawberry.type(get_collection(ProfileOutput, "ProfilesCollection"),
                                     description="Collection of profiles")
