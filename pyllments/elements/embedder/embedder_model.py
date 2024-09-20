import param

from pyllments.base.model_base import Model
from pyllments.payloads.chunk.chunk_payload import ChunkPayload
from pyllments.payloads.message.message_payload import MessagePayload
from .encoders import SentenceTransformerEncoder


class EmbedderModel(Model):
    encoder_model = param.Parameter(default=None)# TODO Make more precise later
    encoder_model_class = param.Parameter(default=SentenceTransformerEncoder, doc=""" # TODO Make more precise later
        Should return a list of embeddings given a list of sentences""")
    encoder_model_name = param.String(default="Alibaba-NLP/gte-base-en-v1.5")

    embedding_dims = param.Integer(default=768, doc="""
        The dimension of the embedding""")
    chunks = param.List(default=[],item_type=ChunkPayload, doc="""
        List of chunks to process""")
    processed_chunks = param.List(default=[], item_type=ChunkPayload, doc="""
        List of processed chunks""")
    messages = param.List(default=[], item_type=MessagePayload, doc="""
        List of messages to process""")
    processed_messages = param.List(default=[], item_type=MessagePayload, doc="""
        List of processed messages""")

    def __init__(self, **params):
        super().__init__(**params)
        self.encoder_model = self.encoder_model_class(model_name=self.encoder_model_name)
        self.embedding_dims = self.encoder_model.embedding_dims
        
        self._set_chunks_watcher()
        self._set_messages_watcher()

    def _set_chunks_watcher(self):
        def fn(event):
            embed_list = self.encoder_model.encode([chunk.model.text for chunk in self.chunks])
            for chunk, embedding in zip(self.chunks, embed_list):
                chunk.model.embedding = embedding
            self.processed_chunks = self.chunks
            with param.parameterized.discard_events(self):
                self.chunks = []
            
        self.param.watch(fn, 'chunks')

    def _set_messages_watcher(self):
        def fn(event):
            embed_list = self.encoder_model.encode([message.model.message.content for message in self.messages])
            for message, embedding in zip(self.messages, embed_list):
                message.model.embedding = embedding
            self.processed_messages = self.messages
            with param.parameterized.discard_events(self):
                self.messages = []

        self.param.watch(fn, 'messages')