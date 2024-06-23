import panel as pn

from pyllments.base import Element
from pyllments.models import ChatInterfaceModel

class ChatInterfaceElement(Element):
    '''Responsible for creating the chat feed, input, and send button views'''
    model = param.ClassSelector(class_=Model, is_instance=True, default=ChatInterfaceModel())

    chatfeed_view = param.ClassSelector(class_=pn.chat.ChatFeed, is_instance=True)
    chat_input_view = param.ClassSelector(class_=pn.chat.ChatAreaInput, is_instance=True)
    send_button_view = param.ClassSelector(class_=pn.widgets.Button, is_instance=True)

    def create_chatfeed_view(self, **kwargs):
        self.chatfeed_view = pn.chat.ChatFeed(**kwargs)
        return self.chatfeed_view
    
    def create_chat_input_view(self, **kwargs):
        self.chat_input_view = pn.chat.ChatAreaInput(**kwargs)
        return self.chat_input_view

    def create_send_button_view(self, **kwargs):
        self.send_button_view = pn.widgets.Button(**kwargs)
        return self.send_button_view

    def _on_send(self, event):
        self.chat_interface_model.message_list.append(('human', self.chat_input_view.value))
        self.chat_input_view.value = ''
        self.chatfeed_view.update()
