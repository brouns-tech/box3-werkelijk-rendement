from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict

from wr.models.base import Record


class InstanceMetadata(Record):
    endpoint: str
    token: str


class StatusResponse(Record):
    ready: bool
    url: str
    pid: int


class FolderResponse(Record):
    folder: str | None


class DataResponse(Record):
    opened: bool


class StopResponse(Record):
    stopping: bool


class LanguagePreference(Record):
    model_config = ConfigDict(extra="ignore")
    language: Literal["nl", "en"]


class LegacyPreferences(Record):
    model_config = ConfigDict(extra="ignore")
    selected_folder: str | None = None


ControlResponse = StatusResponse | FolderResponse | DataResponse | StopResponse
