from abc import ABC
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from enum import Enum
from typing import Optional, Union, Any
from uuid import UUID

from django.db.models import Model


@dataclass
class CommonModel(ABC):
    @classmethod
    def from_dict(cls, data: dict) -> 'CommonModel':
        class_attributes = [attr.name for attr in fields(cls) if attr.init]
        return cls(**{k: cls.deserialize(k, data.get(k)) for k in class_attributes})  # noqa

    def to_dict(self) -> dict:
        return {k: self.serialize(k, v) for k, v in asdict(self).items()}

    @staticmethod
    def deserialize(name: str, obj: Any):
        return obj

    def serialize(self, name: str, obj: Any):
        if isinstance(obj, CommonModel):
            obj = obj.to_dict()
        if isinstance(obj, dict):
            obj = {k: self.serialize(k, v) for k, v in obj.items()}
        return obj


@dataclass
class User:
    email: str
    username: str

    @classmethod
    def from_model(cls, model: Model) -> 'User':
        return cls(username=model.username, email=model.email)


@dataclass
class Workspace(CommonModel):
    id: UUID
    title: str
    config: 'WorkspaceConfig'

    @classmethod
    def from_model(cls, model: Model) -> 'Workspace':
        config = WorkspaceConfig.from_dict(model.config)
        return cls(id=model.id, title=model.title, config=config)

    @classmethod
    def deserialize(cls, name: str, obj: Any):
        if name == 'config':
            obj = WorkspaceConfig.from_dict(obj)
        else:
            obj = super().deserialize(name, obj)
        return obj


@dataclass
class WorkspaceConfig(CommonModel):
    is_active: bool
    plan_id: Optional[str] = None
    deactivation_date: Optional[str] = None
    template_version: Optional[str] = None
    license: Optional[Union['PlatformLicense']] = None

    @classmethod
    def deserialize(cls, name, obj):
        if name == 'license':
            obj = PlatformLicense.from_dict(obj)
        else:
            obj = super().deserialize(name, obj)
        return obj


@dataclass
class License(CommonModel):
    is_trial: bool
    expiry_date: Optional[datetime]
    subscription_id: Optional[str]

    @property
    def config(self) -> dict:
        return {k: self.serialize(k, v) for k, v in asdict(self).items()}

    def serialize(self, name, obj):
        if isinstance(obj, datetime):
            obj = obj.isoformat()
        else:
            obj = super().serialize(name, obj)
        return obj

    @classmethod
    def deserialize(cls, name, obj):
        if name == 'expiry_date':
            obj = datetime.fromisoformat(obj)
        else:
            obj = super().deserialize(name, obj)
        return obj


@dataclass
class MeterAttribute(CommonModel):
    limit: Optional[int] = None
    uses: int = 0
    gross_uses: int = 0
    allowed: Optional[int] = None
    title: str = ''
    plan: str = ''
    stripe_item_id: str = ''
    product_id: Optional[str] = None
    additional_properties: Optional[dict] = None

    def __post_init__(self):
        if self.additional_properties is None:
            self.additional_properties = {}
        if self.allowed is None:
            self.allowed = self.limit


@dataclass
class PlatformLicense(License):
    channels: MeterAttribute
    transactions: 'Transactions'

    @dataclass
    class Transactions:
        tps_limit: int

    @classmethod
    def deserialize(cls, name, obj):
        if name == 'channels':
            obj = MeterAttribute.from_dict(obj)
        else:
            obj = super().deserialize(name, obj)
        return obj


class MultiValueEnum(str, Enum):
    def __new__(cls, *values):
        obj = str.__new__(cls, values[0])
        # first value is canonical value
        obj._value_ = values[0]
        for other_value in values[1:]:
            cls._value2member_map_[other_value] = obj
        obj._all_values = values
        return obj

    def __repr__(self):
        return '<%s.%s: %s>' % (
            self.__class__.__name__,
            self._name_,
            ', '.join([repr(v) for v in self._all_values]),
        )


class SubscriptionStatus(MultiValueEnum):
    ACTIVE = 'active',
    CANCELED = 'canceled'
    UNPAID = 'unpaid', 'incomplete', 'incomplete_expired'
    PAST_DUE = 'past_due'
    TRIALING = 'trialing'
