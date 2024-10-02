from typing import Union

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

        self._message_input_setup()
        self._processed_message_output_setup()

    def _chunks_input_setup(self):
        def process_chunks(chunk_payloads: Union[list[ChunkPayload], ChunkPayload]):
            chunks = chunk_payloads if isinstance(chunk_payloads, list) else [chunk_payloads]
            processed_chunks = self.model.embed_chunks(chunks)
            self.ports.output['processed_chunks_output'].stage_emit(processed_chunks=processed_chunks)

        self.ports.add_input(name='chunk_input', unpack_payload_callback=process_chunks)

    def _processed_chunks_output_setup(self):
        def pack(processed_chunks: list[ChunkPayload]) -> list[ChunkPayload]:
            return processed_chunks

        self.ports.add_output(name='processed_chunks_output', pack_payload_callback=pack)

    def _message_input_setup(self):
        def process_message(message_payload: MessagePayload):
            processed_message = self.model.embed_message(message_payload)
            self.ports.output['processed_message_output'].stage_emit(processed_message=processed_message)

        self.ports.add_input(name='message_input', unpack_payload_callback=process_message)

    def _processed_message_output_setup(self):
        def pack(processed_message: MessagePayload) -> MessagePayload:
            return processed_message

        self.ports.add_output(name='processed_message_output', pack_payload_callback=pack)