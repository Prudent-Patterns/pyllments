from pyllments.elements import ChatInterfaceElement, PipeElement
from pyllments.serve import flow


@flow
def create_gui():
    chat_el = ChatInterfaceElement()
    pipe_el = PipeElement()

    