from pathlib import Path

import param

from pyllments.base.model_base import Model


class FileModel(Model):
    filename = param.String(doc='Name of file')
    b_file = param.ClassSelector(class_=bytes, doc='Bytes object of file')
    local_path = param.ClassSelector(class_=Path, doc='Local path of file')
    remote_path = param.ClassSelector(class_=Path, doc='Remote path of file')