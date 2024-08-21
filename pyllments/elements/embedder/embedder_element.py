from typing import Union

import param

from pyllments.base.element_base import Element
from pyllments.elements.embedder.embedder_model import EmbedderModel
from pyllments.payloads.chunk import ChunkPayload

class EmbedderElement(Element):

    def __init__(self, **params):
        super().__init__(**params)
        self.model = EmbedderModel()
        self._chunk_input_setup()
        self._embedding_output_setup()

    def _chunk_input_setup(self):
        def unpack(chunk_payloads: Union[list[ChunkPayload], ChunkPayload]):
            self.model.chunk_payloads = (chunk_payloads
                                         if isinstance(chunk_payloads, list) 
                                         else [chunk_payloads])
        self.ports.add_input(name='chunk_input', unpack_payload_callback=unpack)

    def _embedding_output_setup(self):
        def pack(processed_chunks: list[ChunkPayload]) -> list[ChunkPayload]:
            return 

        self.ports.add_output(name='embedding_output', pack_payload_callback=pack)

    def _set_watchers(self):
        self._set_processed_chunks_watcher()
    
    def _set_processed_chunks_watcher(self):
        def fn(event):
            self.ports.output['embedding_output'].stage_emit(processed_chunks=self.model.processed_chunks)
            with param.parameterized.disable_events():
                self.model.processed_chunks = [] # Clean up
        self.model.param.watch(fn, 'processed_chunks')  