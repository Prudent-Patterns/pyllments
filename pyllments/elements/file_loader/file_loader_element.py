import param
import panel as pn

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.elements.file_loader.file_loader_model import FileLoaderModel
from pyllments.payloads.file import FilePayload


class FileLoaderElement(Element):
    file_input_view = param.ClassSelector(class_=pn.Column, doc="""
        View responsible for selecting files, and uploading them""")
    file_container_view = param.ClassSelector(class_=pn.Column, doc="""
        View responsible for displaying the files""")
    file_loader_view = param.ClassSelector(class_=pn.Column, doc="""
        View responsible for displaying the file input and file container""")
    file_send_view = param.ClassSelector(class_=pn.widgets.Button, doc="""
        View responsible for sending the files to the server""")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = FileLoaderModel()

        # self._file_output_setup()
    def _file_output_setup(self):
        def pack(file_list: list[FilePayload]) -> list[FilePayload]:
            return file_list
        
        self.ports.add_output('file_list_output', pack)


    def _create_watchers(self):
        self._create_file_list_watcher()

    # def _create_file_list_watcher(self):
    #     def on_file_list_change(event):
    #         self.ports.output['file_list_output'].stage_emit('file_list', event.obj)
    #     self.model.param.watch(on_file_list_change, 'file_list')
            
    @Component.view
    def create_file_input_view(self, input_css: list = []):
        """Creates the 'Add Files Here' Button"""
        def new_file(event):
            obj = event.obj
            for filename, b_file, mime_type in zip(obj.filename, obj.b_file, obj.mime_type):
                self.model.stage_file(filename, b_file, mime_type)
            if not self.file_send_view:
                self.stage_emit(self.model.file_list)

        file_input = pn.widgets.FileInput(
            multiple=True, stylesheets=input_css, sizing_mode="stretch_width")
        file_input.param.watch(new_file, 'value')
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
    
    @Component.view
    def create_file_send_view(
        self,
        button_css: list = [],
        width: int = None,
        height: int = None):
        """Creates the button to send the files to the server"""
        file_send_view = pn.widgets.Button(
            name='Send Files',
            icon='upload',
            stylesheets=button_css,
            width=width,
            height=height)
        file_send_view.on_click(self.model.save_files)
        return file_send_view