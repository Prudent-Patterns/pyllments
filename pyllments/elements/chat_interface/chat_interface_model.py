import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload

class ChatInterfaceModel(Model):
    message_list = param.List(default=[], per_instance=True)
    
    def __init__(self, **params):
        super().__init__(**params)
        self.param.add_parameter(
            'created_message',
            param.ClassSelector(class_=MessagePayload)
        )
        self.message_list.append(('human', 'what is the capital of the moon?'))
