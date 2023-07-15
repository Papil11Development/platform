from typing import List

from pydantic import BaseModel, Extra, Field


class SampleObject(BaseModel):
    class Config:
        extra = Extra.allow
