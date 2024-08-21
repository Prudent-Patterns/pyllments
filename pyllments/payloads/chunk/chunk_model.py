import param

from pyllments.base.model_base import Model
from pyllments.payloads.file import FilePayload


class ChunkModel(Model):
    text = param.String(doc='Text of chunk')
    source_file = param.ClassSelector(class_=FilePayload, doc='Source paylod of chunk')
    strategy = param.String(doc='Strategy used to create chunk', allow_None=True)
    start_idx = param.Integer(allow_None=True, doc="""
        Start index of chunk in source file""")
    end_idx = param.Integer(allow_None=True, doc="""
        End index of chunk in source file""")
    embedding = param.Parameter(doc=""" # TODO: Type this properly
        Embedding of chunk""")