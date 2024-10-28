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
            # logger.info(f"Watcher triggered: old={id(event.old) if event.old else None}, new={id(event.new)}")
            if (
                event.new  # Make sure we have a new message
                and event.new.model.mode == 'stream'  # Check mode on the new message
                and not event.new.model.streamed  # Check streamed status on the new message
                and event.old is not event.new
                ):  # Only proceed if message actually changed
                await event.new.model.stream()
            self.message_list.append(self.new_message)

        self.param.watch(
            _new_message_updated, 
            'new_message', 
            precedence=10,
            onlychanged=True  # Only trigger for actual changes
        )

    # @param.depends('new_message', watch=True)
    # def _log_new_message(self):
    #     logger.info(f"new_message set to {id(self.new_message)}")

