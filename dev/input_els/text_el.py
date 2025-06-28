import panel as pn

from pyllments import flow
from pyllments.elements import TextElement

text_el_in = TextElement()
text_el_out = TextElement()
text_el_out.ports.message_output > text_el_in.ports.message_input

@flow
def main():
    return pn.Row(
        text_el_out.create_input_view(height=800, width=500, title="Output"),
        pn.Spacer(width=6),
        text_el_in.create_interface_view(height=800, width=500, input_title="Input")
    )