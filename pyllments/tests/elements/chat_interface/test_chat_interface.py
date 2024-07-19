from pyllments.elements.chat_interface.chat_interface_element import ChatInterfaceElement
from pyllments.payloads.message import MessagePayload


def stream_chat_interface_test():
    chat_interface_element = ChatInterfaceElement()

    def word_generator(sentence):
        words = sentence.split()
        for word in words:
            yield word

    stream = word_generator("my name is llm shady")

    new_payload  = MessagePayload(mode='stream')
    new_payload.model.stream_obj = stream
    
    chat_interface_element.model.new_message = new_payload
    
    assert chat_interface_element.model.message_list[0] is new_payload