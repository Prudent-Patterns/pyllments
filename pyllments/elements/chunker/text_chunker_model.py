import param

from pyllments.base.model_base import Model
from pyllments.elements.chunker.splitters import base_text_splitter

class TextChunkerModel(Model):
    
    chunk_size = param.Integer(default=1000, doc="""
        The size of the chunks to be created""")
    chunk_overlap = param.Integer(default=200, doc="""
        The overlap of the chunks to be created""")
        
    # For ease for modification, returns named tuples to be processed by the model
    splitter_fn = param.Callable(default=base_text_splitter, doc="""
        Should return a list of Chunk Payloads given a File Payload""")
    file_types = param.List(default=['txt', 'md'])
    multi_proc = param.Boolean(default=False, doc="""
        When True, multiple processes will handle the files simultaneously""")
    file_payloads = param.List(default=[], doc="""List of files to chunk""")
    chunk_payloads = param.List(default=[], doc="""List of chunk payloads""")
    
    def __init__(self, **params):
        super().__init__(**params)
        self._set_watchers()

    def _set_watchers(self):
        self._set_file_list_watcher()

    def _set_file_list_watcher(self):
        def fn(event):
            for file_payload in self.file_payloads:
                for chunk in self.splitter_fn(file_payload):
                    self.chunk_payloads.append(
                        ChunkPayload(
                            text=chunk.text,
                            source_file=file_payload.path,
                            start_idx=chunk.start_index,
                            end_idx=chunk.end_index
                        )
                    )
                self.param.trigger('chunk_payloads') # To let the model know that the chunk_payloads have been updated
            with param.parameterized.disable_events():
                self.file_payloads = [] # Clean up
        self.param.watch(fn, 'file_payloads')