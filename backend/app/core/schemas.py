"""Base class for every API schema: snake_case in Python, camelCase in JSON (like Wesco's API)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,  # trigger_phrases <-> "triggerPhrases" in JSON
        populate_by_name=True,  # accept both names on input; lets Python code use snake_case
        from_attributes=True,  # can be built from a SQLAlchemy object (model_validate(orm_obj))
    )
