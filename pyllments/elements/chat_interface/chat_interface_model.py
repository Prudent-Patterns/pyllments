import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class ChatInterfaceModel(Model):
    # TODO: Implement batch interface for messages - populating message_list > iterating
    message_list = param.List(instantiate=True)
    persist = param.Boolean(default=False, instantiate=True) # TODO: Implement persisting messages to disk
    new_message = param.ClassSelector(class_=MessagePayload)
    
    def __init__(self, **params):
        super().__init__(**params)

        self._create_watchers()

    def _create_watchers(self):
        self.param.watch(
            self._new_message_updated, 'new_message', precedence=10
            )

    def _new_message_updated(self, event):
        if self.new_message.model.mode == 'stream':
            self.new_message.model.stream()
        self.message_list.append(self.new_message)