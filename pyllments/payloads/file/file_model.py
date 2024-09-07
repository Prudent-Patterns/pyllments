from pathlib import Path

import param

from pyllments.base.model_base import Model


class FileModel(Model):
    filename = param.String(doc='Name of file')
    b_file = param.ClassSelector(class_=bytes, doc='Bytes object of file')
    local_path = param.String(default='', doc='Local path of file')
    remote_path = param.String(default='', doc='Remote path of file')
    mime_type = param.String(default='', doc='Mime type of file')