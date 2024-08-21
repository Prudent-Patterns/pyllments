import param

from pyllments.base.model_base import Model
from .encodings import base_sentence_transformer_encode

class EmbedderModel(Model):
    encoder_fn = param.Callable(default=base_sentence_transformer_encode, doc="""
        Should return a list of embeddings given a list of sentences""")
    chunks = param.List(default=[], doc="""List of chunks""")
    processed_chunks = param.List(default=[], doc="""List of processed chunks""")

    def __init__(self, **params):
        super().__init__(**params)
        self._set_watchers()

    def _set_watchers(self):
        self._set_chunks_watcher()

    def _set_chunks_watcher(self):
        def fn(event):
            embed_list = self.embedder_fn([chunk.text for chunk in self.chunks])
            for chunk, embedding in zip(self.chunks, embed_list):
                chunk.embedding = embedding
            self.processed_chunks = self.chunks
            with param.parameterized.disable_events():
                self.chunks = []
            
        self.param.watch(fn, 'chunks')