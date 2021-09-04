import uuid
from enum import Enum
from typing import Optional, List, Union, Tuple

from celery import current_app
from django.db import transaction
from django.conf import settings
from django.db.models import Q

from label_domain.models import Label
from platform_lib.exceptions import BadInputDataException


class LabelManager:

    class Types(str, Enum):
        LOCATION = Label.LOCATION
        PROFILE_GROUP = Label.PROFILE_GROUP
        AREA_TYPE = Label.AREA_TYPE

    def __init__(self, workspace_id: str, label_id: Optional[str] = None):
        self.workspace_id = workspace_id
        self.label = None
        if label_id is not None:
            self.label = Label.objects.get(
                workspace_id=self.workspace_id,
                id=label_id
            )

    def get_label(self) -> Optional[Label]:
        return self.label

    @staticmethod
    def get_label_by_id(label_id: Union[str, uuid.UUID]) -> Optional[Label]:
        try:
            return Label.objects.get(id=label_id)
        except Label.DoesNotExist:
            return None

    def change_label_info(self, info: Optional[dict] = None, title: Optional[str] = None):
        with transaction.atomic():
            if info is not None:
                self.label.info.update(info)
            if title:
                self.label.title = title
            self.label.save()

    def delete_labels(self, label_ids: List[str], label_type: Types):
        from user_domain.managers import WorkspaceManager

        with transaction.atomic():
            labels = Label.objects.select_for_update().filter(
                id__in=label_ids,
                workspace_id=self.workspace_id,
                type=label_type.value
            )
            if labels.count() != len(set(label_ids)):
                raise BadInputDataException("0x573bkd35")

            for label in labels:
                label.profiles.clear()

            labels.delete()

        template_version = (WorkspaceManager.get_template_version(self.workspace_id)
                            or settings.DEFAULT_TEMPLATES_VERSION)

        for label_id in label_ids:
            current_app.tasks['data_domain.tasks.delete_index'].delay(
                index=label_id,
                template_version=template_version
            )

    def create_label(self, info: Optional[dict], title: str, label_type: Optional[str] = None) -> Label:
        if info is None:
            info = {}

        with transaction.atomic():
            label = Label.objects.create(
                workspace_id=self.workspace_id,
                type=label_type,
                title=title,
                info=info
            )

        return label

    @staticmethod
    def create_default_labels(workspace_id: str,
                              label_titles: List[str] = settings.DEFAULT_PROFILE_LABEL_TITLES) -> List[Label]:
        label_manager = LabelManager(workspace_id=workspace_id)

        return [label_manager.create_label(title=str(title), label_type=Label.PROFILE_GROUP, info={"color": "red.600"})
                for title in label_titles]

    @staticmethod
    def get_label_data(label_id: str) -> Tuple[Optional[str], dict]:
        label = Label.objects.all(Q(is_active__in=[True, False], id=label_id)).first()
        return getattr(label, "title", None), getattr(label, "info", {})
