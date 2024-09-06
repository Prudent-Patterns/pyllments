import param

from pyllments.base.model_base import Model
from pyllments.payloads.file.file_payload import FilePayload


class FileLoaderModel(Model):
    save_to_disk = param.Boolean(default=False, doc='Whether to save the files to disk')
    file_dir = param.String(default='', doc='Directory which files are saved to')
    # TODO: Async file saving when batched
    file_list = param.List(default=[], doc='List of files')
    
    def __init__(self, **params):
        super().__init__(**params)
        
        self._create_watchers()

    def stage_file(self, filename: str, b_file: bytes, mime_type: str = None):
        self.file_list.append(FilePayload(filename=filename, b_file=b_file, mime_type=mime_type))

    def save_files(self):
        for file in self.file_list:
            with open(self.file_dir, "wb") as file:
                file.write(file.b_file)

    def _create_watchers(self):
        if self.save_to_disk:
            self.param.watch(self.save_file, 'b_file')
