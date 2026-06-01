from __future__ import annotations

from typing import Any, List, TYPE_CHECKING, Union

import param

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.payloads import MessagePayload, ToolsResponsePayload
from pyllments.runtime.loop_registry import LoopRegistry

from .history_handler_model import HistoryHandlerModel

if TYPE_CHECKING:
    import panel as pn

PayloadInput = Union[
    MessagePayload,
    ToolsResponsePayload,
    List[MessagePayload],
    List[ToolsResponsePayload],
]


class HistoryHandlerElement(Element):
    """
    Canonical timeline manager: raw ledger, tiered projection, summarization candidates.

    Ports
    -----
    payload_input : ingest without emission
    payload_emit_input : ingest and emit context + summary candidates
    summary_input : summarizer artifacts (e.g. StructuredPayload)
    context_output : projected payload list for ContextBuilderElement
    summary_candidate_output : full raw spans for SummarizerElement
    """

    show_tool_responses = param.Boolean(
        default=False,
        doc="Include tool response views in the history panel.",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self.context_view = None
        self.model = HistoryHandlerModel(**params)

        self._payload_input_setup()
        self._payload_emit_input_setup()
        self._summary_input_setup()
        self._context_output_setup()
        self._summary_candidate_output_setup()

    @staticmethod
    async def _normalize_payloads(payload: PayloadInput) -> List[Any]:
        if isinstance(payload, list):
            items = payload
        else:
            items = [payload]
        for item in items:
            if hasattr(item, "model") and hasattr(item.model, "await_ready"):
                await item.model.await_ready()
        return items

    @staticmethod
    def _supported_only(items: List[Any]) -> List[Any]:
        return [
            p
            for p in items
            if isinstance(p, (MessagePayload, ToolsResponsePayload))
        ]

    async def _emit_outputs(self):
        context = self.model.get_context_payloads()
        await self.ports.output["context_output"].stage_emit(context=context)

        candidates = self.model.get_summary_candidate_payloads()
        if candidates:
            await self.ports.output["summary_candidate_output"].stage_emit(
                context=candidates
            )

    def _payload_input_setup(self):
        async def unpack(payload: PayloadInput):
            async def _handle():
                items = await self._normalize_payloads(payload)
                supported = self._supported_only(items)
                if supported:
                    self.model.load_entries(supported)

            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name="payload_input", unpack_payload_callback=unpack)

    def _payload_emit_input_setup(self):
        async def unpack(payload: PayloadInput):
            async def _handle():
                items = await self._normalize_payloads(payload)
                supported = self._supported_only(items)
                if supported:
                    self.model.load_entries(supported)
                    await self._emit_outputs()

            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name="payload_emit_input", unpack_payload_callback=unpack)

    def _summary_input_setup(self):
        async def unpack(payload: Any):
            async def _handle():
                if hasattr(payload, "model") and hasattr(payload.model, "await_ready"):
                    await payload.model.await_ready()
                self.model.accept_summary_artifact(payload)

            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name="summary_input", unpack_payload_callback=unpack)

    def _context_output_setup(self):
        async def pack(context: list) -> list:
            return context

        self.ports.add_output(
            name="context_output",
            pack_payload_callback=pack,
        )

    def _summary_candidate_output_setup(self):
        async def pack(context: list) -> list:
            return context

        self.ports.add_output(
            name="summary_candidate_output",
            pack_payload_callback=pack,
        )

    @Component.view
    def create_context_view(
        self,
        title: str = "Current History",
        column_css: list = [],
        container_css: list = [],
        title_css: list = [],
        title_visible: bool = True,
    ) -> pn.Column:
        """Display raw payloads in the current projected context window."""
        import panel as pn

        views = []
        for entry in self.model.get_context_entries_for_view():
            payload = entry.payload
            if isinstance(payload, MessagePayload):
                views.append(payload.create_collapsible_view())
            elif self.show_tool_responses and isinstance(payload, ToolsResponsePayload):
                views.append(payload.create_collapsible_view())

        context_container = pn.Column(
            *views,
            scroll=True,
            sizing_mode="stretch_both",
            stylesheets=container_css,
        )
        self.context_view = pn.Column(
            pn.pane.Markdown(
                f"### {title}",
                visible=title_visible,
                stylesheets=title_css,
                sizing_mode="stretch_width",
            ),
            context_container,
            stylesheets=column_css,
            scroll=False,
        )

        async def _update_context_view(event):
            entries = self.model.get_context_entries_for_view()
            context_container.objects = []
            for entry in entries:
                payload = entry.payload
                if isinstance(payload, MessagePayload):
                    context_container.append(payload.create_collapsible_view())
                elif self.show_tool_responses and isinstance(payload, ToolsResponsePayload):
                    context_container.append(payload.create_collapsible_view())
            context_container.param.trigger("objects")

        self.watch(self.model, "history", _update_context_view)
        return self.context_view
