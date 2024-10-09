import param
import panel as pn

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.elements.file_loader.file_loader_model import FileLoaderModel
from pyllments.payloads.file import FilePayload


class FileLoaderElement(Element):
    file_input_view = param.ClassSelector(class_=pn.widgets.FileInput, doc="View responsible for selecting files, and uploading them")
    file_container_view = param.ClassSelector(class_=pn.Column, doc="View responsible for displaying the files")
    file_loader_view = param.ClassSelector(class_=pn.Column, doc="View responsible for displaying the file input and file container")
    file_send_view = param.ClassSelector(class_=pn.widgets.Button, doc="View responsible for sending the files to the server")

    def __init__(self, file_dir: str = '', **params):
        super().__init__(**params)
        self.model = FileLoaderModel(file_dir=file_dir)

        self._file_output_setup()

    def _file_output_setup(self):
        def pack(file_list: list[FilePayload]) -> list[FilePayload]:
            return file_list
        
        self.ports.add_output('file_list_output', pack)

    @Component.view
    def create_file_input_view(self, input_css: list = [], sizing_mode: str = 'stretch_width', width: int = None):
        """Creates the 'Add Files Here' Button"""
        def new_file(event):
            obj = event.obj
            for filename, b_file, mime_type in zip(obj.filename, obj.value, obj.mime_type):
                file_payload = self.model.stage_file(filename, b_file, mime_type)
                if isinstance(self.file_container_view, pn.Column):
                    self.file_container_view.append(file_payload.create_file_view())
            if not self.file_send_view: # When there's no send button automatically emit
                self.emit_files()  
        self.file_input_view = pn.widgets.FileInput(
            multiple=True, stylesheets=input_css, sizing_mode=sizing_mode, width=width)
        self.file_input_view.param.watch(new_file, 'value')
        return self.file_input_view
    
    @Component.view
    def create_file_container_view(self, container_css: list = [], sizing_mode: str = "stretch_both", height: int = None, width: int = None):
        """Creates the container holding a visual of the uploaded files"""
        self.file_container_view = pn.Column(
            stylesheets=container_css,
            sizing_mode=sizing_mode,
            height=height,
            width=width,
            scroll=True)
        for file in self.model.file_list:
            self.file_container_view.append(file.create_file_view())

        return self.file_container_view
    
    @Component.view
    def create_file_send_view(self, button_css: list = [], sizing_mode: str = 'stretch_width', width: int = None, height: int = None):
        """Creates the button to send the files to the server"""
        self.file_send_view = pn.widgets.Button(
            name='Send Files',
            icon='upload',
            stylesheets=button_css,
            width=width,
            height=height,
            sizing_mode=sizing_mode,
            align='center')
        self.file_send_view.on_click(self.emit_files)
        return self.file_send_view

    @Component.view
    def create_file_loader_view(self, sizing_mode: str = 'stretch_both', width: int = None, height: int = None):
        """Creates a composition of the button and file container"""
        file_input_view = self.create_file_input_view()
        file_container_view = self.create_file_container_view()
        file_send_view = self.create_file_send_view()

        self.file_loader_view = pn.Column(
            file_input_view,
            file_container_view, 
            file_send_view, 
            width=width, 
            height=height, 
            sizing_mode=sizing_mode)
        return self.file_loader_view

    def emit_files(self, event=None):
        """Manually trigger file emission when the send button is clicked."""
        self.model.save_files()

        self.ports.output['file_list_output'].stage_emit(file_list=self.model.file_list)

        self.clear_files()

    def clear_files(self):
        """Clear the files from both the model and the view."""
        self.model.clear_files()

        if isinstance(self.file_container_view, pn.Column):
            self.file_container_view.clear()
