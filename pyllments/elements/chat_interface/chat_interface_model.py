import param
import asyncio # TODO: remove after debugging

from loguru import logger # TODO: remove after debugging
from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class ChatInterfaceModel(Model):
    # TODO: Implement batch interface for messages - populating message_list > iterating
    message_list = param.List(instantiate=True, item_type=MessagePayload)
    persist = param.Boolean(default=False, instantiate=True) # TODO: Implement persisting messages to disk
    new_message = param.ClassSelector(class_=MessagePayload)
    
    def __init__(self, **params):
        super().__init__(**params)

        self._create_new_message_watcher()

    def _create_new_message_watcher(self):
        async def _new_message_updated(event):
            if not event.new or event.old is event.new:  # Skip if no message or same message
                return
                
            if (event.new.model.mode == 'stream' 
                and not event.new.model.streamed):  # Handle streaming AI messages
                await event.new.model.stream()
            
            self.message_list.append(event.new)  # Add message regardless of type

        self.param.watch(
            _new_message_updated, 
            'new_message', 
            precedence=10,
            onlychanged=True
        )

    # @param.depends('new_message', watch=True)
    # def _log_new_message(self):
    #     logger.info(f"new_message set to {id(self.new_message)}")

