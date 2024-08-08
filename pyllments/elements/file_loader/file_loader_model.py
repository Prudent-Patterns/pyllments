import param

from pyllments.base.model_base import Model


class FileLoaderModel(Model):
    save_to_disk = param.Boolean(default=False, doc='Whether to save the file to disk')
    file_dir = param.String(default='', doc='Directory which files are saved to')
    # TODO: Async file saving when batched
    b_file = param.ClassSelector(class_=bytes, doc='Bytes object of file')
    file_list = param.List(default=[], doc='List of files')
    
    def __init__(self, **params):
        super().__init__(**params)
        
        self._create_watchers()

    def save_file(self):
        with open(self.file_dir, "wb") as file:
            file.write(self.b_file)

    def _create_watchers(self):
        if self.save_to_disk:
            self.param.watch(self.save_file, 'b_file')
