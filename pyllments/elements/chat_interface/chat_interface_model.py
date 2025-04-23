import param
import asyncio

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.tools_response import ToolsResponsePayload

class ChatInterfaceModel(Model):
    # TODO: Implement batch interface for messages - populating message_list > iterating
    message_list = param.List(instantiate=True, item_type=(MessagePayload, ToolsResponsePayload))
    persist = param.Boolean(default=False, instantiate=True) # TODO: Implement persisting messages to disk
    
    def __init__(self, **params):
        super().__init__(**params)

    async def add_message(self, payload: MessagePayload | ToolsResponsePayload):
        """
        Centralized handler for new messages and tool responses:
          - Streams AI messages when in streaming mode.
          - Calls tools for tool response payloads.
          - Appends the processed payload to the message_list.
        """
        if isinstance(payload, MessagePayload):
            if payload.model.mode == 'stream' and not payload.model.streamed:
                await payload.model.stream()
        elif isinstance(payload, ToolsResponsePayload):
            # Only auto-call tools if none require permission; otherwise defer to the view prompting logic
            requires_perm = any(
                resp.get('permission_required', False)
                for resp in (payload.model.tool_responses or {}).values()
            )
            if not payload.model.called and not payload.model.calling and not requires_perm:
                await payload.model.call_tools()
        self.message_list.append(payload)
        self.param.trigger('message_list')
