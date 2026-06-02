from __future__ import annotations

from typing import Any, List, Optional

import param

from pyllments.base.model_base import Model
from pyllments.elements.context_builder.to_message import payload_message_mapping, to_message_payload
from pyllments.payloads import MessagePayload, StructuredPayload
from pyllments.payloads.structured.summary_contract import (
    build_summary_artifact,
    summary_request_fields,
)


DEFAULT_SUMMARY_INSTRUCTIONS = """You summarize conversation history for later use in an LLM context window.

Preserve:
- User goals, constraints, and decisions
- Important facts, names, numbers, and outcomes
- Tool calls and tool results that matter for future turns

Omit:
- Redundant phrasing and filler
- Repeated content already captured elsewhere

Write in clear prose. Do not invent information not present in the source material."""


DEFAULT_SUMMARY_FORMAT_PROMPT = (
    "Write a single concise summary of the conversation span above. "
    "Use markdown only if it improves clarity."
)


class SummarizerModel(Model):
    """Prompt assembly and summary artifact construction for SummarizerElement."""

    summary_instructions = param.String(
        default=DEFAULT_SUMMARY_INSTRUCTIONS,
        doc="System instructions describing summarization policy.",
    )
    summary_format_prompt = param.String(
        default=DEFAULT_SUMMARY_FORMAT_PROMPT,
        doc="Final user message asking the model to produce the summary.",
    )
    strategy = param.String(
        default="default",
        allow_None=True,
        doc="Optional strategy label stored on emitted summary StructuredPayload.",
    )

    def build_messages_from_request(
        self,
        request: StructuredPayload,
    ) -> List[MessagePayload]:
        """Turn a summary request into LLM chat messages."""
        source_payloads, _, instructions = summary_request_fields(request)
        policy = instructions or self.summary_instructions
        return self.build_messages_from_sources(source_payloads, instructions=policy)

    def build_messages_from_sources(
        self,
        source_payloads: List[Any],
        instructions: Optional[str] = None,
    ) -> List[MessagePayload]:
        """Convert heterogeneous history payloads into an ordered message list."""
        policy = instructions or self.summary_instructions
        messages: List[MessagePayload] = [MessagePayload(role="system", content=policy)]

        for item in source_payloads:
            converted = self._convert_source_item(item)
            if isinstance(converted, list):
                messages.extend(converted)
            elif converted is not None:
                messages.append(converted)

        messages.append(MessagePayload(role="user", content=self.summary_format_prompt))
        return messages

    def _convert_source_item(self, item: Any) -> Any:
        if isinstance(item, list):
            if not item:
                return None
            item_types = {type(p) for p in item}
            if len(item_types) > 1:
                messages: List[MessagePayload] = []
                for payload in item:
                    part = to_message_payload(
                        payload,
                        payload_message_mapping,
                        expected_type=type(payload),
                    )
                    if isinstance(part, list):
                        messages.extend(part)
                    else:
                        messages.append(part)
                return messages
            return to_message_payload(
                item,
                payload_message_mapping,
                expected_type=list[type(item[0])],
            )
        return to_message_payload(
            item,
            payload_message_mapping,
            expected_type=type(item),
        )

    def build_summary_payload(
        self,
        content: str,
        source_entry_ids: Optional[List[str]] = None,
        model_name: Optional[str] = None,
    ) -> StructuredPayload:
        """Package LLM output as a history-ready structured summary artifact."""
        return build_summary_artifact(
            content=content,
            source_entry_ids=source_entry_ids,
            strategy=self.strategy,
            model_name=model_name,
        )
