from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AntispoofingRequest(_message.Message):
    __slots__ = ["data"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    data: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, data: _Optional[_Iterable[bytes]] = ...) -> None: ...

class AntispoofingResponse(_message.Message):
    __slots__ = ["confidence", "isReal"]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    ISREAL_FIELD_NUMBER: _ClassVar[int]
    confidence: float
    isReal: bool
    def __init__(self, isReal: bool = ..., confidence: _Optional[float] = ...) -> None: ...
