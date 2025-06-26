from __future__ import annotations

from typing import Any

import panel as pn
import param
from loguru import logger

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.runtime.loop_registry import LoopRegistry
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.schema import SchemaPayload
from pyllments.payloads.structured import StructuredPayload

from .structured_output_model import StructuredOutputModel


class StructuredOutputElement(Element):
    """Element that advertises a schema to downstream elements and turns
    assistant messages that *should* comply with that schema into validated
    :class:`StructuredPayload`s.

    Ports
    -----
    input
        • **message_emit_input** (MessagePayload) – assistant messages coming back from the LLM.
    output
        • **schema_output** (SchemaPayload) – emitted once (or whenever the schema param changes).
        • **structured_output** (StructuredPayload) – validated dict emitted after each message.
    """

    json_view = param.ClassSelector(class_=pn.pane.JSON, allow_None=True)

    def __init__(self, schema: type | None = None, auto_emit_schema: bool = True, **params):
        super().__init__(**params)
        # store schema in the model
        self.model = StructuredOutputModel(schema=schema)

        # internal view placeholder
        self.json_view = None

        # setup ports *before* auto-emitting
        self._setup_ports()

        # emit schema right away so downstream elements can receive it
        if auto_emit_schema and schema is not None:
            self.emit_schema()

    # ---------------------------------------------------------------------
    # Port setup
    # ---------------------------------------------------------------------
    def _setup_ports(self):
        """Declare and wire the three ports."""

        # ---- schema_output ------------------------------------------------
        async def pack_schema() -> SchemaPayload:  # pragma: no cover
            return SchemaPayload(schema=self.model.schema)

        async def _emit_on_connect(output_port, input_port):
            """Emit current schema immediately after a connection is made."""
            await output_port.stage_emit_to(input_port)

        self.ports.add_output(
            name="schema_output",
            pack_payload_callback=pack_schema,
            on_connect_callback=_emit_on_connect,
        )

        # ---- structured_output -------------------------------------------
        async def pack_structured(structured_data: dict[str, Any]) -> StructuredPayload:  # pragma: no cover
            return StructuredPayload(data=structured_data)

        self.ports.add_output(
            name="structured_output",
            pack_payload_callback=pack_structured,
        )

        # ---- message_emit_input ------------------------------------------
        async def unpack_message(payload: MessagePayload):
            """Validate incoming assistant message and emit structured payload."""
            try:
                # Ensure content is ready (handles stream / atomic transparently)
                await payload.model.await_ready()
                structured_dict = self.model.validate_message(payload.model.content)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"StructuredOutputElement: failed to validate message – {exc}")
                return

            # Update optional JSON view
            if self.json_view is not None:
                self.json_view.object = structured_dict

            # Emit to downstream listeners
            await self.ports.output["structured_output"].stage_emit(structured_data=structured_dict)

        self.ports.add_input(
            name="message_emit_input",
            unpack_payload_callback=unpack_message,
            payload_type=MessagePayload,
        )

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def emit_schema(self):
        """Convenience helper to push the *current* schema through *schema_output*."""
        loop = LoopRegistry.get_loop()
        loop.create_task(self.ports.output["schema_output"].stage_emit())

    # ---------------------------------------------------------------------
    # Views ----------------------------------------------------------------
    # ---------------------------------------------------------------------
    @Component.view
    def create_output_view(
        self,
        height: int | None = 300,
        sizing_mode: str = "stretch_width",
        json_theme: str = "light",
        depth: int = 5,
    ) -> pn.pane.JSON:
        """Return a live-updating JSON pane that shows the latest structured data."""
        self.json_view = pn.pane.JSON(
            object=None,
            height=height,
            sizing_mode=sizing_mode,
            depth=depth,
            theme=json_theme,
        )
        return self.json_view
