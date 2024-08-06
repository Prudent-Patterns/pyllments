import param
import panel as pn

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.elements.file_loader.file_loader_model import FileLoaderModel

class FileLoaderElement(Element):
    file_upload_view = param.ClassSelector(class_=pn.Column, doc="""
        View responsible for selecting files, and uploading them""")
    
    def __init__(self, **params):
        super().__init__(**params)
        self.model = FileLoaderModel()

        # self._file_output_setup()
    
    @Component.view
    def create_file_input_view(self, input_css: list = []):
        """Creates the 'Add Files Here' Button"""

        file_input = pn.widgets.FileInput(
            multiple=True, stylesheets=input_css, sizing_mode="stretch_width")
        return file_input
    
    @Component.view
    def create_file_container_view(
        self,
        container_css: list = [],
        sizing_mode: str = "stretch_both",
        height: int = None,
        width: int = None):
        """Creates the container holding a visual of the uploaded files"""
        file_container = pn.Column(
            stylesheets=container_css,
            sizing_mode=sizing_mode,
            height=height,
            width=width)
        for file in self.model.file_list:
            file_container.append(file.create_file_view())

        return file_container

    @Component.view
    def create_file_loader_view(
        self,
        width: int = None,
        height: int = None):
        file_input_view = self.create_file_input_view()
        file_container = self.create_file_container_view(
            sizing_mode='stretch_both')
        """Creates a composition of the button and file container"""

        return pn.Column(
            file_input_view, file_container, width=width, height=height)