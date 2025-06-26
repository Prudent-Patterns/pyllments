from __future__ import annotations

import json
from typing import Any

import param
from pydantic import BaseModel
from pydantic.root_model import RootModel

from pyllments.base.model_base import Model


class StructuredOutputModel(Model):
    """Model responsible for holding a schema definition and turning raw
    JSON strings coming back from an LLM into validated Python dictionaries.
    """

    # NOTE: We store the *class* (not instance) of a pydantic model so that we
    #       can instantiate it per-validation.  Both ``BaseModel`` subclasses
    #       and ``RootModel`` (pydantic-v2 single-value models) are accepted.
    schema = param.ClassSelector(
        class_=(BaseModel, RootModel),
        is_instance=False,
        allow_None=True,
        doc="The pydantic schema used to validate/parse the LLM response",
    )

    def validate_message(self, message: str) -> dict[str, Any]:
        """Validate *message* against the stored schema and return a dict.

        Parameters
        ----------
        message : str
            Raw JSON string coming from a :class:`MessagePayload`.

        Returns
        -------
        dict
            The structured data as parsed by *schema* and converted to a dict.
        """
        if self.schema is None:
            raise ValueError("`schema` is not set on StructuredOutputModel – cannot validate message.")

        # First parse the JSON – we expect the assistant to return JSON text.
        try:
            payload_obj = json.loads(message)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to decode JSON from assistant message: {exc}") from exc

        # Instantiate the pydantic model to validate & coerce types.
        try:
            model_instance = self.schema.model_validate(payload_obj)  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback for pydantic<2 or custom models that don't have `model_validate`
            model_instance = self.schema(**payload_obj)

        # Return a plain Python dict representation.
        return model_instance.model_dump()  # type: ignore[return-value]
