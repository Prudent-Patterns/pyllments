from typing import Union, List

import param

from pyllments.base.element_base import Element
from pyllments.elements.embedder.embedder_model import EmbedderModel
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload


class EmbedderElement(Element):
    """
    Element that generates embeddings for chunks and messages, passing them through with
    the embeddings attached to the Payloads.
    """
    def __init__(self, **params):
        super().__init__(**params)
        self.model = EmbedderModel(**params)
        
        self._chunks_input_setup()
        self._processed_chunks_output_setup()

        self._messages_input_setup()
        self._processed_messages_output_setup()

    def _chunks_input_setup(self):
        def process_chunks(chunk_payloads: Union[List[ChunkPayload], ChunkPayload]):
            chunks = chunk_payloads if isinstance(chunk_payloads, list) else [chunk_payloads]
            processed_chunks = self.model.embed_chunks(chunks)
            self.ports.output['processed_chunks_output'].stage_emit(processed_chunks=processed_chunks)

        self.ports.add_input(name='chunk_input', unpack_payload_callback=process_chunks)

    def _processed_chunks_output_setup(self):
        def pack(processed_chunks: List[ChunkPayload]) -> List[ChunkPayload]:
            return processed_chunks

        self.ports.add_output(name='processed_chunks_output', pack_payload_callback=pack)

    def _messages_input_setup(self):
        def process_messages(message_payloads: Union[List[MessagePayload], MessagePayload]):
            messages = message_payloads if isinstance(message_payloads, list) else [message_payloads]
            processed_messages = self.model.embed_messages(messages)
            self.ports.output['processed_messages_output'].stage_emit(processed_messages=processed_messages)

        self.ports.add_input(name='message_input', unpack_payload_callback=process_messages)

    def _processed_messages_output_setup(self):
        def pack(processed_messages: List[MessagePayload]) -> List[MessagePayload]:
            return processed_messages

        self.ports.add_output(name='processed_messages_output', pack_payload_callback=pack)