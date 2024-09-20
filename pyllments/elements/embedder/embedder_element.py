from typing import Union

import param

from pyllments.base.element_base import Element
from pyllments.elements.embedder.embedder_model import EmbedderModel
from pyllments.payloads.chunk import ChunkPayload

class EmbedderElement(Element):
    """
    Element that generates embeddings for chunks and messages, passing them through with
    the embeddings attached to the Payloads.
    """
    def __init__(self, **params):
        super().__init__(**params)
        self.model = EmbedderModel()
        
        self._chunks_input_setup()
        self._processed_chunks_output_setup()
        self._set_processed_chunks_watcher()

        self._messages_input_setup()
        self._processed_messages_output_setup()
        self._set_processed_messages_watcher()

    def _chunks_input_setup(self):
        def unpack(chunk_payloads: Union[list[ChunkPayload], ChunkPayload]):
            self.model.chunks = (chunk_payloads
                                if isinstance(chunk_payloads, list) 
                                else [chunk_payloads])
        self.ports.add_input(name='chunk_input', unpack_payload_callback=unpack)

    def _processed_chunks_output_setup(self):
        def pack(processed_chunks: list[ChunkPayload]) -> list[ChunkPayload]:
            return processed_chunks

        self.ports.add_output(name='processed_chunks_output', pack_payload_callback=pack)
    
    def _set_processed_chunks_watcher(self):
        def fn(event):
            self.ports.output['processed_chunks_output'].stage_emit(processed_chunks=self.model.processed_chunks)
            with param.parameterized.discard_events(self.model):
                self.model.processed_chunks = [] # Clean up
        self.model.param.watch(fn, 'processed_chunks')

    def _messages_input_setup(self):
        def unpack(message_payloads: Union[list[MessagePayload], MessagePayload]):
            self.model.messages = (message_payloads
                                if isinstance(message_payloads, list) 
                                else [message_payloads])
        self.ports.add_input(name='message_input', unpack_payload_callback=unpack)

    def _processed_messages_output_setup(self):
        def pack(processed_messages: list[MessagePayload]) -> list[MessagePayload]:
            return processed_messages

        self.ports.add_output(name='processed_messages_output', pack_payload_callback=pack)

    def _set_processed_messages_watcher(self):
        def fn(event):
            self.ports.output['processed_messages_output'].stage_emit(processed_messages=self.model.processed_messages)
            with param.parameterized.discard_events(self.model):
                self.model.processed_messages = [] # Clean up
        self.model.param.watch(fn, 'processed_messages')