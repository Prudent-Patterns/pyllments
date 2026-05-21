from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncIterator

from pyllments.payloads.message.stream_events import MessageStreamEvent

if TYPE_CHECKING:
    from pyllments.payloads import MessagePayload
    from pyllments.elements.chat_gateway.chat_gateway_element import ChatGatewayElement


class TurnHandle:
    """
    Application-facing handle for a single chat turn.

    Parameters
    ----------
    turn_id : str
        Unique turn identifier.
    user_message : MessagePayload
        The user message emitted into the flow.
    gateway : ChatGatewayElement
        Gateway element used to bind responses, cancellation, and tool events.
    """

    def __init__(self, turn_id: str, user_message: MessagePayload, gateway: ChatGatewayElement):
        self.turn_id = turn_id
        self.user_message = user_message
        self._gateway = gateway
        self._gateway_model = gateway.model
        self._assistant_linked = asyncio.Event()

    async def _wait_for_assistant(self) -> MessagePayload:
        assistant = await self._gateway_model.wait_for_assistant(self.turn_id)
        self._assistant_linked.set()
        return assistant

    async def stream(self) -> AsyncIterator[MessageStreamEvent]:
        """
        Yield stream events from the assistant response for this turn.

        Raises
        ------
        asyncio.CancelledError
            If the turn was cancelled before or during streaming.
        RuntimeError
            If the turn was cancelled and no assistant message arrives.
        """
        if self._gateway_model.is_turn_cancelled(self.turn_id):
            yield MessageStreamEvent(type='cancelled')
            return

        assistant = await self._wait_for_assistant()
        if self._gateway_model.is_turn_cancelled(self.turn_id):
            assistant.model.cancel()
            yield MessageStreamEvent(type='cancelled')
            return

        async for event in assistant.model.aiter_events():
            if self._gateway_model.is_turn_cancelled(self.turn_id):
                assistant.model.cancel()
                yield MessageStreamEvent(type='cancelled')
                return
            if event.type == 'tool_calls_complete' and event.tool_calls:
                await self._gateway.emit_tool_event(self.turn_id, event.tool_calls)
            yield event
            if event.type == 'cancelled':
                return
            if event.type == 'done':
                self._gateway_model.complete_turn(self.turn_id)

    async def final_message(self) -> MessagePayload:
        """
        Return the assistant message payload after the stream completes.

        Consumes the stream when it has not been read yet.
        """
        if self._gateway_model.is_turn_cancelled(self.turn_id):
            raise RuntimeError(f"Turn {self.turn_id} was cancelled")

        assistant = await self._wait_for_assistant()
        if not assistant.model.streamed and not assistant.model.cancelled:
            await assistant.model.aget_message()
        await assistant.model.await_ready()
        self._gateway_model.complete_turn(self.turn_id)
        return assistant

    def cancel(self) -> None:
        """Cancel this turn and stop provider token generation when possible."""
        self._gateway_model.cancel_turn(self.turn_id)
