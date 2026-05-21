from __future__ import annotations

import asyncio

import param

from pyllments.base.element_base import Element
from pyllments.payloads import MessagePayload, StructuredPayload
from pyllments.payloads.message.stream_events import MessageStreamEvent
from pyllments.runtime.loop_registry import LoopRegistry
from pyllments.elements.chat_gateway.chat_gateway_model import ChatGatewayModel
from pyllments.elements.chat_gateway.turn_handle import TurnHandle


class ChatGatewayElement(Element):
    """
    Production boundary for driving Pyllments chat flows from application code.

    Provides submit/receive/cancel without Panel or blocking HTTP futures. Connect
    ``message_output`` into your context/history path and ``assistant_message_input``
    from ``LLMChatElement.message_output``. Optionally connect ``tool_events_output``
    to an MCP or custom tool executor (outline only in phase 1).

    Ports
    -----
    message_output : out
        Emits user ``MessagePayload`` instances into the flow.
    assistant_message_input : in
        Receives assistant ``MessagePayload`` instances from the LLM element.
    tool_events_output : out
        Emits tool-call completion events as ``StructuredPayload`` for downstream routing.

    Examples
    --------
    >>> turn = gateway.submit_message("Hello")
    >>> async for event in turn.stream():
    ...     broker.publish(event)
    >>> assistant = await turn.final_message()
    """

    default_aggregate_stream = param.Boolean(
        default=True,
        doc="Default aggregate_stream for assistant stream payloads (history compatibility)",
    )

    _ELEMENT_PARAMS = frozenset({'default_aggregate_stream'})

    def __init__(self, **params):
        super().__init__(**params)
        model_params = {
            key: value
            for key, value in params.items()
            if key not in self._ELEMENT_PARAMS
        }
        self.model = ChatGatewayModel(**model_params)
        self._setup_ports()

    def _setup_ports(self):
        self._message_output_setup()
        self._assistant_message_input_setup()
        self._tool_events_output_setup()

    def _message_output_setup(self):
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload

        self.ports.add_output(name='message_output', pack_payload_callback=pack)

    def _assistant_message_input_setup(self):
        async def unpack(payload: MessagePayload):
            turn_id = self.model.match_turn(payload)
            if turn_id is None:
                self.logger.warning("Received assistant message with no pending turn; ignoring")
                return

            state = self.model.get_turn_state(turn_id)
            if state is None or state.cancelled:
                payload.model.cancel()
                return

            if payload.model.mode == 'stream':
                payload.model.aggregate_stream = self.default_aggregate_stream

        self.ports.add_input(
            name='assistant_message_input',
            unpack_payload_callback=unpack,
            payload_type=MessagePayload,
        )

    def _tool_events_output_setup(self):
        async def pack(payload: dict) -> StructuredPayload:
            return StructuredPayload(data=payload)

        self.ports.add_output(name='tool_events_output', pack_payload_callback=pack)

    async def emit_tool_event(self, turn_id: str, tool_calls: list[dict]) -> None:
        """
        Outline: emit tool call completion for downstream MCP or custom tool routing.
        """
        if self.model.is_turn_cancelled(turn_id):
            return
        await self.ports.output['tool_events_output'].stage_emit(
            payload={
                'turn_id': turn_id,
                'tool_calls': tool_calls,
            }
        )

    async def submit_message_async(self, content: str, role: str = 'user', **kwargs) -> TurnHandle:
        """
        Async variant that awaits emission onto ``message_output``.
        """
        turn_id = self.model.create_turn_id()
        user_message = MessagePayload(content=content, role=role, correlation_id=turn_id, **kwargs)
        self.model.register_turn(turn_id, user_message)
        await self.ports.output['message_output'].stage_emit(payload=user_message)
        return TurnHandle(turn_id=turn_id, user_message=user_message, gateway=self)

    def submit_message(self, content: str, role: str = 'user', **kwargs) -> TurnHandle:
        """
        Inject a user message into the flow and return a turn handle.

        Parameters
        ----------
        content : str
            Message text.
        role : str
            Message role (default ``user``).
        **kwargs
            Additional ``MessagePayload`` / ``MessageModel`` parameters.

        Returns
        -------
        TurnHandle
            Handle for streaming and cancellation.
        """
        turn_id = self.model.create_turn_id()
        user_message = MessagePayload(content=content, role=role, correlation_id=turn_id, **kwargs)
        self.model.register_turn(turn_id, user_message)

        loop = LoopRegistry.get_loop()
        loop.create_task(
            self.ports.output['message_output'].stage_emit(payload=user_message)
        )
        return TurnHandle(turn_id=turn_id, user_message=user_message, gateway=self)

    def cancel(self, turn_id: str) -> None:
        """Cancel an in-flight turn by id."""
        self.model.cancel_turn(turn_id)
