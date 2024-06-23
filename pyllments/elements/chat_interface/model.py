from pyllments.base import Model
from pyllments.elements import MessageElement

class ChatInterfaceModel(Model):
    message_list = param.List(default=[], per_instance=True)
    created_message = param.ClassSelector(class_=MessageElement)
    
    def __init__(self, **params):
        super().__init__(**params)
        self.message_list.append(('human', 'what is the capital of the moon?'))
