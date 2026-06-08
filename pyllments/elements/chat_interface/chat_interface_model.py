import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.tool_use import ToolUsePayload


class ChatInterfaceModel(Model):
    # TODO: Implement batch interface for messages - populating message_list > iterating
    message_list = param.List(instantiate=True, item_type=(MessagePayload, ToolUsePayload))
    persist = param.Boolean(default=False, instantiate=True)

    def __init__(self, **params):
        super().__init__(**params)

    async def add_message(self, payload: MessagePayload | ToolUsePayload):
        """
        Centralized handler for new messages and tool use payloads.
        """
        if isinstance(payload, MessagePayload):
            if payload.model.mode == 'stream' and not payload.model.streamed:
                await payload.model.stream()
            elif payload.model.mode == 'atomic':
                try:
                    await payload.model.aget_message()
                except AttributeError:
                    pass
        elif isinstance(payload, ToolUsePayload):
            await payload.model.await_ready()

        self.message_list.append(payload)
        self.param.trigger('message_list')
