import panel as pn

from pyllments.base.payload_base import Payload
from pyllments.base.component_base import Component
from pyllments.payloads.chunk.chunk_model import ChunkModel

class ChunkPayload(Payload):
    def __init__(self, **params):
        super().__init__(**params)
        self.model = ChunkModel(**params)

    @Component.view
    def create_collapsible_view(
        self,
        button_css: list = [],
        markdown_css: list = [],
        row_css: list = [],
        truncation_length: int = 40
        ):

        expand_button = pn.widgets.Toggle(
            icon='plus',
            icon_size='1.1em',
            button_type='primary',
            button_style='outline',
            stylesheets=button_css)
        

        source_text = f"""
            <span class='chunk_header'>Source:</span>\n
            <span class='source_text'>{self.model.source_filepath}</span>\n

            """
        content_header = f"""
            <span class='chunk_header'>Content:</span>\n
            """
        content_text = f"""
            <span class='content_text'>{self.model.text}</span>
            """
        truncated_content_text = f"""
            <span class='content_text'>{self.model.text[:truncation_length]}</span>
            """
        
        markdown = pn.pane.Markdown(
            source_text + content_header + truncated_content_text,
            stylesheets=markdown_css
            )
        
        def toggle_visibility(event):
            if event.new:
                expand_button.icon = 'minus'
                markdown.object = source_text + content_header + content_text
            else:
                expand_button.icon = 'plus'
                markdown.object = source_text \
                    + content_header \
                    + truncated_content_text
        
        expand_button.param.watch(toggle_visibility, 'value')

        view = pn.Row(
            expand_button,
            markdown,
            sizing_mode='stretch_width',
            stylesheets=row_css
            )
        
        return view
        