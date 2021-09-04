import uuid
from typing import Optional, List, Tuple, Union, Iterable

from django.db import transaction
from django.conf import settings
from django.db.models import QuerySet

from user_domain.managers import WorkspaceManager
import platform_lib.utils
from user_domain.models import Workspace
from label_domain.models import Label
from person_domain.models import Person, Profile
from data_domain.models import Activity, Sample
from data_domain.matcher.main import MatcherAPI
from platform_lib.types import ElasticAction
from platform_lib.exceptions import BadInputDataException, InvalidJsonRequest
from platform_lib.validation import is_valid_json
from platform_lib.validation.schemes import profile_info_scheme
from celery import current_app


class PersonManager:
    def __init__(self, workspace_id: str, person_id: Optional[str] = None):
        self.workspace_id = workspace_id
        self.person = None
        if person_id:
            self.person = Person.objects.get(workspace_id=self.workspace_id, id=person_id)

    def get_person(self) -> Person:
        return self.person

    def get_persons_profile(self) -> Profile:
        return self.person.profile

    @staticmethod
    def create_person(workspace: Workspace, id: Optional[str] = None, profile_info: Optional[dict] = None) -> Person:
        if profile_info is None:
            profile_info = {}

        if not is_valid_json(profile_info, profile_info_scheme):
            raise InvalidJsonRequest()

        with transaction.atomic():
            if id:
                person = Person.objects.create(id=id, workspace=workspace, info=profile_info)
            else:
                person = Person.objects.create(workspace=workspace, info=profile_info)

        return person

    @classmethod
    def merge_persons(cls, source_person_id, activities_ids, target_person_id):
        pass
        # source_person = Person.objects.get(id=source_person_id)
        # target_person = Person.objects.get(id=target_person_id)
        #
        # if source_person == target_person:
        #     raise BadInputDataException("0x81dcd1d4")
        #
        # with transaction.atomic():
        #     if activities_ids:
        #         filter_ = Q(person=source_person) & Q(id__in=activities_ids)
        #     else:
        #         filter_ = Q(person=source_person)
        #
        #     activities_to_update = Activity.objects.select_for_update().filter(filter_)
        #
        #     if activities_to_update.count() == 0:
        #         raise BadInputDataException("0x581bd57e")
        #
        #     activities_to_update.update(person=target_person)
        #     for activity in activities_to_update:
        #         for blob in activity.blobs:
        #             blob.sample.update(profile=target_person.profile)
        #
        #     if Activity.objects.filter(Q(person=source_person)).count() == 0:
        #         source_person.delete()
        #
        # cls.__set_base(str(target_person.workspace.id))
        # cls.__drop_elastic_index(str(target_person.workspace.id))
        # return target_person

    @classmethod
    def delete_persons(cls, workspace_id, person_ids: list):
        with transaction.atomic():
            workspace = Workspace.objects.get(id=workspace_id)

            if not person_ids:
                raise BadInputDataException("0xd2ae0ef8")

            persons = Person.objects.select_for_update().filter(id__in=person_ids, workspace=workspace)
            if persons.count() != len(set(person_ids)):
                raise BadInputDataException("0x51b4c0e2")
            persons.delete()
        cls.__set_base_remove(workspace, person_ids)
        cls.__drop_elastic_index(str(workspace.id), person_ids)

    @staticmethod
    def __set_base_remove(workspace, person_ids):
        template_version = workspace.config.get(
            'template_version',
            settings.DEFAULT_TEMPLATES_VERSION
        )
        MatcherAPI.set_base_remove(str(workspace.id), template_version, person_ids)

    @staticmethod
    @platform_lib.utils.elk_checker
    def __drop_elastic_index(workspace_id, person_ids):
        current_app.tasks['data_domain.tasks.elastic_manager'].delay(
            action=ElasticAction.drop, person_ids=person_ids, workspace_id=workspace_id
        )


class ProfileManager:
    def __init__(self, workspace_id: str, profile_id: str):
        self.workspace_id = workspace_id
        self.profile: Profile = Profile.objects.get(workspace_id=self.workspace_id, id=profile_id)
        self.current_groups_ids = None

    @staticmethod
    def _add_to_indexes(indexes: Iterable[str], workspace_id: str, profile: Profile):
        from data_domain.managers import SampleManager

        template_version = (WorkspaceManager.get_template_version(workspace_id)
                            or settings.DEFAULT_TEMPLATES_VERSION)

        sample = SampleManager.get_sample(
            workspace_id=workspace_id,
            sample_id=profile.info['main_sample_id'],
        )

        template_id = SampleManager.get_template_id(sample.meta, template_version)

        templates_info = [{'id': template_id, 'personId': str(profile.person_id)}]
        for index_key in indexes:
            current_app.tasks['data_domain.tasks.add_to_index'].delay(
                index=str(index_key),
                template_version=template_version,
                templates_info=templates_info
            )

    @staticmethod
    def _remove_from_indexes(indexes: Iterable[str], workspace_id: str, person_ids: List[str]):
        template_version = (WorkspaceManager.get_template_version(workspace_id)
                            or settings.DEFAULT_TEMPLATES_VERSION)

        for index_key in indexes:
            current_app.tasks['data_domain.tasks.remove_from_index'].delay(
                index=str(index_key),
                template_version=template_version,
                person_ids=person_ids
            )

    def get_profile(self) -> Profile:
        return self.profile

    def get_label_ids(self, label_ids: list) -> QuerySet:
        labels = Label.objects.filter(workspace_id=self.workspace_id, id__in=label_ids,
                                      type=Label.PROFILE_GROUP).values_list('id', flat=True)
        if labels.count() != len(set(label_ids)):
            raise BadInputDataException("0x573bkd35")
        return labels

    def get_sample_ids(self, sample_ids: list) -> QuerySet:
        samples = Sample.objects.filter(workspace_id=self.workspace_id, id__in=sample_ids).values_list('id', flat=True)
        if samples.count() != len(set(sample_ids)):
            raise BadInputDataException("0x943b3c24")
        return samples

    def add_samples(self, sample_ids: Optional[list]) -> Profile:
        if sample_ids is not None:
            with transaction.atomic():
                self.profile.samples.add(*self.get_sample_ids(sample_ids=sample_ids))
                self.profile.save()
        return self.profile

    def delete_profile_main_sample(self):
        with transaction.atomic():
            self.profile.samples.remove(self.profile.info['main_sample_id'])
            self.profile.info['main_sample_id'] = None
            self.profile.save()

    def add_labels(self, label_ids: Optional[list]) -> Profile:
        if label_ids is not None:
            with transaction.atomic():
                self.current_groups_ids = {str(pg_id) for pg_id in
                                           self.profile.profile_groups.values_list('id', flat=True)}
                self.profile.profile_groups.add(*self.get_label_ids(label_ids=label_ids))
                self.profile.save()

            if self.profile.info.get('main_sample_id'):
                labels_to_index = set(label_ids) - self.current_groups_ids
                self._add_to_indexes(labels_to_index, self.workspace_id, self.profile)

        return self.profile

    def remove_labels(self, label_ids: Optional[list]) -> Profile:
        if label_ids is not None:
            with transaction.atomic():
                self.profile.profile_groups.remove(*self.get_label_ids(label_ids=label_ids))
                self.profile.save()

            self._remove_from_indexes(label_ids, self.workspace_id, [str(self.profile.person_id)])

        return self.profile

    @classmethod
    @transaction.atomic
    def create_with_person(cls,
                           workspace: Workspace,
                           info: Optional[dict] = None,
                           label_ids: Optional[list] = None,
                           sample_ids: Optional[list] = None,
                           person_id: Optional[str] = None) -> Tuple[Profile, Person]:
        person = PersonManager.create_person(workspace, person_id, info)
        profile = cls.create(workspace, person, info, label_ids, sample_ids)

        return profile, person

    @classmethod
    @transaction.atomic
    def create(cls, workspace: Workspace, person: Person, info: Optional[dict] = None,
               label_ids: Optional[list] = None, sample_ids: Optional[list] = None):
        profile = Profile.objects.create(workspace=workspace, person=person, info=info)
        profile_manager = cls(str(workspace.id), str(profile.id))
        profile_manager.add_labels(label_ids)
        profile_manager.add_samples(sample_ids)

        return profile_manager.get_profile()

    @staticmethod
    def delete(workspace_id: str, profile_id: str):
        profile = Profile.objects.get(workspace_id=workspace_id, id=profile_id)
        PersonManager.delete_persons(workspace_id, [profile.person.id])

    @staticmethod
    def delete_profiles(workspace_id: str, profile_ids: List[Union[str, uuid.UUID]]):
        profiles = Profile.objects.filter(workspace_id=workspace_id, id__in=profile_ids)
        if profiles.count() != len(set(profile_ids)):
            raise BadInputDataException("0x51b4c0e2")
        label_ids = set()
        person_ids = list()
        for profile in profiles:
            person_ids.append(str(profile.person_id))
            [label_ids.add(str(label)) for label in profile.profile_groups.values_list('id', flat=True)]

        PersonManager.delete_persons(workspace_id, person_ids)

        ProfileManager._remove_from_indexes(label_ids, workspace_id, person_ids)

    def update(self, info=None, label_ids: Optional[list] = None, sample_ids: Optional[list] = None) -> Profile:
        with transaction.atomic():
            locked_profile = Profile.objects.select_for_update().get(id=self.profile.id)
            if info is not None:
                locked_profile.info.update(info)
            if label_ids is not None:
                current_groups_ids = {str(pg_id) for pg_id
                                      in locked_profile.profile_groups.values_list('id', flat=True)}
                locked_profile.profile_groups.set(self.get_label_ids(label_ids))
            if sample_ids is not None:
                locked_profile.samples.add(*self.get_sample_ids(sample_ids=sample_ids))
            locked_profile.save()

        if label_ids is not None:
            # A set of elements that occur in one set but do not occur in both sets with update current_groups_ids set
            current_groups_ids.symmetric_difference_update(label_ids)

            self._remove_from_indexes(current_groups_ids, self.workspace_id, [str(self.profile.person_id)])
            self._add_to_indexes(current_groups_ids, self.workspace_id, self.profile)

        self.profile.refresh_from_db()

        return self.profile
