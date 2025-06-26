from pyllments import flow
from pyllments.elements import TextElement

text_el = TextElement()

@flow
def main():
    return text_el.create_interface_view(height=800, width=500)