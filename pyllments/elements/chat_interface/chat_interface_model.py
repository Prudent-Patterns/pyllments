import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.tools_response import ToolsResponsePayload

class ChatInterfaceModel(Model):
    # TODO: Implement batch interface for messages - populating message_list > iterating
    message_list = param.List(instantiate=True, item_type=(MessagePayload, ToolsResponsePayload))
    persist = param.Boolean(default=False, instantiate=True) # TODO: Implement persisting messages to disk
    new_message = param.ClassSelector(class_=(MessagePayload, ToolsResponsePayload))
    
    def __init__(self, **params):
        super().__init__(**params)

        self._create_new_message_watcher()

    def _create_new_message_watcher(self):
        async def _new_message_updated(event):
            if not event.new or (event.old is event.new):  # Skip if no message or same message
                return
            if isinstance(event.new, MessagePayload):
                if (event.new.model.mode == 'stream' 
                    and not event.new.model.streamed):  # Handle streaming AI messages
                    await event.new.model.stream()
            elif isinstance(event.new, ToolsResponsePayload):
                pass
            self.message_list.append(event.new)  # Add message regardless of type

        self.param.watch(
            _new_message_updated, 
            'new_message', 
            precedence=10,
            onlychanged=True
        )
