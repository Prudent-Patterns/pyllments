from __future__ import annotations

from typing import List, Union

import param

from pyllments.base.element_base import Element
from pyllments.elements.llm_chat.litellm_chat_model import LiteLLMChatModel
from pyllments.elements.llm_chat.openrouter_chat_model import OpenRouterChatModel
from pyllments.payloads import MessagePayload, StructuredPayload, ToolsResponsePayload
from pyllments.payloads.structured.summary_contract import summary_request_fields
from pyllments.runtime.loop_registry import LoopRegistry

from .summarizer_model import SummarizerModel

PayloadListInput = Union[
    MessagePayload,
    ToolsResponsePayload,
    List[MessagePayload],
    List[ToolsResponsePayload],
    List[Union[MessagePayload, ToolsResponsePayload]],
]


class SummarizerElement(Element):
    """
    Summarizes history spans via an internal LLM chat model.

    Ports
    -----
    summary_request_emit_input : StructuredPayload summary_request from HistoryHandler
    payloads_emit_input : ad hoc payload list without ledger entry IDs
    summary_output : StructuredPayload summary artifact for HistoryHandler.summary_input
    """

    backend = param.Selector(
        objects=["openrouter", "litellm"],
        default="openrouter",
        doc="Chat backend used for summarization.",
    )

    def __init__(self, **params):
        super().__init__(**params)
        element_param_names = {"backend", "summary_instructions", "summary_format_prompt", "strategy"}
        model_params = {
            key: value
            for key, value in params.items()
            if key not in element_param_names
        }
        summarizer_params = {
            key: value
            for key, value in params.items()
            if key in {"summary_instructions", "summary_format_prompt", "strategy"}
        }
        self.model = SummarizerModel(**summarizer_params)

        self._chat_model_init_params = {
            key: value
            for key, value in model_params.items()
            if key not in summarizer_params
        }
        self._chat_model_init_params.setdefault("output_mode", "atomic")
        self.chat_model = self._create_chat_model(self.backend, self._chat_model_init_params)

        self._summary_request_emit_input_setup()
        self._payloads_emit_input_setup()
        self._summary_output_setup()

    def _filter_model_params(self, model_cls, model_params: dict) -> dict:
        accepted_params = set(model_cls.param.objects().keys())
        return {key: value for key, value in model_params.items() if key in accepted_params}

    def _create_chat_model(self, backend: str, model_params: dict):
        params = dict(model_params)
        params["output_mode"] = "atomic"
        if backend == "openrouter":
            params.pop("base_url", None)
            return OpenRouterChatModel(**self._filter_model_params(OpenRouterChatModel, params))
        if backend == "litellm":
            return LiteLLMChatModel(**self._filter_model_params(LiteLLMChatModel, params))
        raise ValueError(f"Unsupported summarizer backend: {backend}")

    async def _summarize_and_emit(
        self,
        messages: List[MessagePayload],
        source_entry_ids: List[str],
    ):
        response = self.chat_model.generate_response(messages)
        await response.model.aget_message()
        summary = self.model.build_summary_payload(
            content=response.model.content,
            source_entry_ids=source_entry_ids,
            model_name=getattr(self.chat_model, "model_name", None),
        )
        await self.ports.output["summary_output"].stage_emit(context=summary)

    def _summary_request_emit_input_setup(self):
        async def unpack(request: StructuredPayload):
            async def _handle():
                messages = self.model.build_messages_from_request(request)
                _, source_entry_ids, _ = summary_request_fields(request)
                await self._summarize_and_emit(messages, source_entry_ids)

            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(
            name="summary_request_emit_input",
            unpack_payload_callback=unpack,
        )

    def _payloads_emit_input_setup(self):
        async def unpack(payload: PayloadListInput):
            async def _handle():
                if isinstance(payload, list):
                    sources = payload
                else:
                    sources = [payload]
                for item in sources:
                    if hasattr(item, "model") and hasattr(item.model, "await_ready"):
                        await item.model.await_ready()
                messages = self.model.build_messages_from_sources(sources)
                await self._summarize_and_emit(messages, [])

            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(
            name="payloads_emit_input",
            unpack_payload_callback=unpack,
        )

    def _summary_output_setup(self):
        async def pack(summary: StructuredPayload) -> StructuredPayload:
            return summary

        self.ports.add_output(
            name="summary_output",
            pack_payload_callback=pack,
        )
