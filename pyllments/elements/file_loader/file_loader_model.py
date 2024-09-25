from pathlib import Path

import param

from pyllments.base.model_base import Model
from pyllments.payloads.file.file_payload import FilePayload


class FileLoaderModel(Model):
    save_to_disk = param.Boolean(default=False, doc='Whether to save the files to disk')
    file_dir = param.String(default='', doc='Directory which files are saved to')
    file_list = param.List(default=[], doc='List of file payloads')
    
    def __init__(self, **params):
        super().__init__(**params)
        if self.file_dir and self.save_to_disk:
            Path(self.file_dir).mkdir(parents=True, exist_ok=True)

    def stage_file(self, filename: str, b_file: bytes, mime_type: str = None) -> FilePayload:
        """
        Create a FilePayload and add it to the file_list.
        
        Parameters:
        -----------
        filename : str
            Name of the file
        b_file : bytes
            Binary content of the file
        mime_type : str, optional
            MIME type of the file
        
        Returns:
        --------
        FilePayload
            The created FilePayload object
        """
        file_payload = FilePayload(
            filename=filename, 
            b_file=b_file, 
            mime_type=mime_type,
            local_path=str(Path(self.file_dir, filename))
        )
        self.file_list.append(file_payload)
        return file_payload

    def save_files(self):
        """Save all files in file_list to disk if save_to_disk is True."""
        if self.save_to_disk:
            for file in self.file_list:
                with open(Path(self.file_dir, file.model.filename), "wb") as f:
                    f.write(file.model.b_file)

    def clear_files(self):
        """Clear the file list."""
        self.file_list = []