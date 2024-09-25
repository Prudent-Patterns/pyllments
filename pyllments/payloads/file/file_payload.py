from typing import Optional
from pathlib import Path

import panel as pn

from pyllments.base.payload_base import Payload
from pyllments.payloads.file.file_model import FileModel
from pyllments.base.component_base import Component


icon_css_map = {
    "file": "ti ti-file",
    "png": "ti ti-file-type-png"}

class FilePayload(Payload):

    def __init__(self, **params):
        super().__init__(**params)
        self.model = FileModel(**params)

    @Component.view
    def create_file_view(
        self,
        width: int = None,
        icon_css: list = [],
        markdown_css: list = [],
        row_css: list = [],
        char_limit: Optional[int] = None):
        """View Responsible for displaying the file icon and filename"""
        # Extract the file suffix from the filename
        file_suffix = self.model.filename.split('.')[-1] if '.' in self.model.filename else ''
        # Default to generic icon if suffix not in mapping
        icon_class = icon_css_map.get(file_suffix, 'ti ti-file')
        icon_html = pn.pane.HTML(
            f"""
            <span class="{icon_class}"></span>
            """,
            stylesheets=icon_css,
            align='center')
        
        filename = self.model.filename
        # If necessary, truncate the filename from the middle and replace with ...
        if char_limit and len(filename) > char_limit:
            # Calculate the number of characters to keep from the start and end
            keep_start = (char_limit - 3) // 2  # 3 for the ellipsis
            keep_end = char_limit - 3 - keep_start
            
            # Create the truncated filename with ellipsis
            filename = f"{filename[:keep_start]}...{filename[-keep_end:]}" if keep_end > 0 else f"{filename[:keep_start]}..."

        markdown = pn.pane.Markdown(
            filename, stylesheets=markdown_css)  
        
        return pn.Row(icon_html, markdown, sizing_mode='stretch_width', width=width, stylesheets=row_css)
