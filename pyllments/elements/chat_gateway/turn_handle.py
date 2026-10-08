from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from pyllments.payloads.message.stream_events import MessageStreamEvent

if TYPE_CHECKING:
    from pyllments.payloads import MessagePayload
    from pyllments.elements.chat_gateway.chat_gateway_element import ChatGatewayElement


class TurnHandle:
    """
    Application-facing handle for a single chat turn.

    One ``stream()`` covers the whole turn, round by round: the reply's events,
    then ``tool_results`` when that reply called tools and the gateway ran
    them, then the next reply, until a reply calls no tools and ``done`` ends
    the turn.

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

    def _terminal_event(self) -> MessageStreamEvent:
        state = self._gateway_model.get_turn_state(self.turn_id)
        if state is not None and state.error:
            return MessageStreamEvent(type='error', error=state.error)
        return MessageStreamEvent(type='cancelled')

    async def _round_events(self, assistant: MessagePayload) -> AsyncIterator[MessageStreamEvent]:
        """A reply's events, with its tool calls as one ``tool_calls_complete``."""
        model = assistant.model
        if model.mode == 'atomic':
            await model.aget_message()
            if model.content:
                yield MessageStreamEvent(type='token', content_delta=model.content)
            if model.tool_calls:
                yield MessageStreamEvent(
                    type='tool_calls_complete', tool_calls=[dict(tc) for tc in model.tool_calls]
                )
            return
        async for event in model.aiter_events():
            if event.type == 'done':
                return
            yield event

    async def stream(self) -> AsyncIterator[MessageStreamEvent]:
        """
        Yield the turn's events across every round.

        ``done`` arrives once, when the turn ends. A cancelled turn yields
        ``cancelled``; a failed one (round budget) yields ``error``.
        """
        model = self._gateway_model
        round_index = 0
        while True:
            if model.is_turn_cancelled(self.turn_id):
                yield self._terminal_event()
                return
            assistant = await model.wait_for_round(self.turn_id, round_index)
            if assistant is None:
                yield self._terminal_event()
                return

            called_tools: list[dict] | None = None
            try:
                async for event in self._round_events(assistant):
                    if model.is_turn_cancelled(self.turn_id):
                        assistant.model.cancel()
                        yield self._terminal_event()
                        return
                    if event.type == 'tool_calls_complete' and event.tool_calls:
                        called_tools = event.tool_calls
                        await self._gateway.emit_tool_event(self.turn_id, event.tool_calls)
                    if event.type == 'error':
                        # The provider failed mid-reply: the turn ends here, as data.
                        model.fail_turn(self.turn_id, str(event.error or 'provider_error'))
                        yield event
                        return
                    yield event
                    if event.type == 'cancelled':
                        return
            except Exception as exc:
                if not model.is_turn_cancelled(self.turn_id):
                    model.fail_turn(self.turn_id, str(exc))
                yield MessageStreamEvent(type='error', error=str(exc))
                return
            if assistant.model.tool_calls and called_tools is None:
                # A reply read before (e.g. final_message after stream) reports its
                # calls only on done; the round still continues.
                called_tools = [dict(tc) for tc in assistant.model.tool_calls]

            if not called_tools or not self._gateway.tools_wired:
                model.complete_turn(self.turn_id)
                yield MessageStreamEvent(type='done', tool_calls=called_tools)
                return

            results = await model.wait_for_tool_results(self.turn_id, round_index)
            if results is None:
                yield self._terminal_event()
                return
            yield MessageStreamEvent(
                type='tool_results',
                tool_results=[dict(record) for record in results.model.tool_calls],
                raw=results,
            )
            round_index += 1

    async def final_message(self) -> MessagePayload:
        """
        Return the last assistant message after the turn completes.

        Consumes whatever of the stream has not been read yet.
        """
        async for event in self.stream():
            if event.type in ('cancelled', 'error'):
                raise RuntimeError(f"Turn {self.turn_id} ended: {event.error or 'cancelled'}")
        state = self._gateway_model.get_turn_state(self.turn_id)
        assert state is not None and state.assistant_message is not None
        return state.assistant_message

    def cancel(self) -> None:
        """Cancel this turn and stop provider token generation when possible."""
        self._gateway_model.cancel_turn(self.turn_id)
