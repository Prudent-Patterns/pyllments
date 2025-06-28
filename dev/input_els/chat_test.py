import panel as pn

from pyllments import flow
from pyllments.elements import ChatInterfaceElement, PipeElement
from pyllments.payloads import MessagePayload

chat_el = ChatInterfaceElement(message_list=[
    MessagePayload(role='user', content='Hello, how are you?'),
    MessagePayload(role='assistant', content='I am good, thank you!'),
    MessagePayload(role='user', content='What is your name?'),
    MessagePayload(role='assistant', content='My name is Assistant.'),
    MessagePayload(role='user', content='What is the weather in Tokyo?'),
    MessagePayload(role='assistant', content='The weather in Tokyo is sunny and warm.'),
    MessagePayload(role='user', content='What is the weather in Tokyo?'),
])

@flow
def main():
    return chat_el.create_interface_view(height=800, width=500)
    