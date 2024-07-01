import panel as pn
import param

from pyllments.base.element_base import Element
from pyllments.base.model_base import Model
from pyllments.elements.chat_interface import ChatInterfaceModel

class ChatInterfaceElement(Element):
    """
    Model:
    - messages in the chat
    - message input
    Views:
    - chat feed
    - chat input
    - send button
    """
    model = param.ClassSelector(
        class_=Model,
        is_instance=True,
        default=ChatInterfaceModel()
    )

    chatfeed_view = param.ClassSelector(class_=pn.chat.ChatFeed, is_instance=True)
    chat_input_view = param.ClassSelector(class_=pn.chat.ChatAreaInput, is_instance=True)
    send_button_view = param.ClassSelector(class_=pn.widgets.Button, is_instance=True)

    def create_chatfeed_view(self, **kwargs):
        """
        Creates and returns a new instance of ChatFeed view.
        """
        self.chatfeed_view = pn.chat.ChatFeed(**kwargs)
        return self.chatfeed_view
    
    def create_chat_input_view(self, **kwargs):
        """
        Creates and returns a new instance of ChatAreaInput view.
        """
        self.chat_input_view = pn.chat.ChatAreaInput(**kwargs)
        return self.chat_input_view

    def create_send_button_view(self, **kwargs):
        """
        Creates and returns a new instance of Button view for sending messages.
        """
        self.send_button_view = pn.widgets.Button(**kwargs)
        return self.send_button_view

    def _on_send(self, event):
        """
        Handles the send button event by appending the user's message to the chat model,
        clearing the input field, and updating the chat feed view.
        """
        self.model.message_list.append(('human', self.chat_input_view.value))
        self.chat_input_view.value = ''
        self.chatfeed_view.update()
