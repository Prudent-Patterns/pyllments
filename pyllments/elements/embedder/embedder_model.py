import param
from typing import List

from pyllments.base.model_base import Model
from pyllments.payloads.chunk.chunk_payload import ChunkPayload
from pyllments.payloads.message.message_payload import MessagePayload
from .encoders import SentenceTransformerEncoder


class EmbedderModel(Model):
    encoder_model = param.Parameter(default=None)
    encoder_model_class = param.Parameter(default=SentenceTransformerEncoder, doc="""
        Should return a list of embeddings given a list of sentences""")
    encoder_model_name = param.String(default="Alibaba-NLP/gte-base-en-v1.5")
    embedding_dims = param.Integer(default=768, doc="The dimension of the embedding")

    def __init__(self, **params):
        super().__init__(**params)
        self.encoder_model = self.encoder_model_class(model_name=self.encoder_model_name)
        self.embedding_dims = self.encoder_model.embedding_dims

    def embed_chunks(self, chunks: List[ChunkPayload]) -> List[ChunkPayload]:
        """
        Embed a list of chunks and return the processed chunks with embeddings.
        """
        embed_list = self.encoder_model.encode([chunk.model.text for chunk in chunks])
        for chunk, embedding in zip(chunks, embed_list):
            chunk.model.embedding = embedding
        return chunks

    def embed_messages(self, messages: List[MessagePayload]) -> List[MessagePayload]:
        """
        Embed a list of messages and return the processed messages with embeddings.
        """
        embed_list = self.encoder_model.encode([message.model.message.content for message in messages])
        for message, embedding in zip(messages, embed_list):
            message.model.embedding = embedding
        return messages