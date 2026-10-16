from __future__ import annotations

from pydantic import BaseModel

from wr.models.metadata import FactMetadata
from wr.models.settings import InstitutionSettings


def parse_institution_settings(issuer: str, value: object) -> InstitutionSettings:
    from wr.parsers._registry import PLUGINS

    model = next((plugin.options_model for plugin in PLUGINS if plugin.issuer == issuer), InstitutionSettings)
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_unset=True)
    if value is not None and not isinstance(value, (dict, InstitutionSettings)):
        raise ValueError(f"institutions.{issuer} must be an object")
    return model.model_validate(value if value is not None else {})


def parse_metadata(issuer: str, value: object) -> FactMetadata:
    from wr.parsers._registry import PLUGINS

    model = next((plugin.metadata_model for plugin in PLUGINS if plugin.issuer == issuer), FactMetadata)
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_unset=True)
    if isinstance(value, str):
        return model.model_validate_json(value)
    return model.model_validate(value if value is not None else {})
