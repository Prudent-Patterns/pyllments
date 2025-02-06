import param

from pyllments.base.model_base import Model
from pyllments.payloads.chunk.chunk_payload import ChunkPayload
from pyllments.payloads.message.message_payload import MessagePayload
from .embedders import SentenceTransformerEmbedder


class EmbedderModel(Model):
    embedder_model = param.Parameter(default=None)
    embedder_model_class = param.Parameter(default=SentenceTransformerEmbedder, doc="""
        Should return a list of embeddings given a list of sentences""")
    embedder_model_name = param.String(default="Alibaba-NLP/gte-base-en-v1.5")
    embedding_dims = param.Integer(default=768, doc="The dimension of the embedding")

    def __init__(self, **params):
        super().__init__(**params)
        self.embedder_model = self.embedder_model_class(model_name=self.embedder_model_name)
        self.embedding_dims = self.embedder_model.embedding_dims

        self.param.watch(self._on_embedder_model_name_change, 'embedder_model_name')

    def embed_chunks(self, chunks: list[ChunkPayload]) -> list[ChunkPayload]:
        """
        Embed a list of chunks and return the processed chunks with embeddings.
        """
        embed_list = self.embedder_model.encode([chunk.model.text for chunk in chunks])
        for chunk, embedding in zip(chunks, embed_list):
            chunk.model.embedding = embedding
        return chunks

    def embed_chunk(self, chunk: ChunkPayload) -> ChunkPayload:
        """
        Embed a chunk and return the processed chunk with embedding.
        """
        chunk = self.embed_chunks([chunk])[0]
        return chunk

    def embed_messages(self, messages: list[MessagePayload]) -> list[MessagePayload]:
        """
        Embed a list of messages and return the processed messages with embeddings.
        """
        
        embed_list = self.embedder_model.encode([message.model.message.content for message in messages])
        for message, embedding in zip(messages, embed_list):
            message.model.embedding = embedding
        return messages
    
    def embed_message(self, message: MessagePayload) -> MessagePayload:
        """
        Embed a message and return the processed message with embedding.
        """
        message = self.embed_messages([message])[0]
        return message
    
    def _on_embedder_model_name_change(self, event):
        self.embedder_model.model_name = self.embedder_model_name
        self.embedding_dims = self.embedder_model.embedding_dims