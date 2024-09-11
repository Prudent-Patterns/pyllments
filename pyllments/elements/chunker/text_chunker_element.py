from typing import Union

import param

from pyllments.base.element_base import Element
from pyllments.elements.chunker.text_chunker_model import TextChunkerModel
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.file import FilePayload


class TextChunkerElement(Element):

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150, **params):
        super().__init__(**params)
        self.model = TextChunkerModel(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        self._file_input_setup()
        self._chunk_output_setup()
        
        self._set_chunk_payloads_watcher()

    def _file_input_setup(self):
        def unpack(payload: Union[FilePayload, list[FilePayload]]):
            file_payload_list = payload if isinstance(payload, list) else [payload]
            self.model.file_payloads = file_payload_list

        self.ports.add_input(name='file_input', unpack_payload_callback=unpack)

    def _chunk_output_setup(self):
        def pack(chunk_payloads: list[ChunkPayload]) -> list[ChunkPayload]:
            with param.parameterized.discard_events(self.model):
                self.model.chunk_payloads = [] # Clean up
            return chunk_payloads
        
        self.ports.add_output(name='chunk_output', pack_payload_callback=pack)

    def _set_chunk_payloads_watcher(self):
        def fn(event):
            self.ports.output['chunk_output'].stage_emit(chunk_payloads=self.model.chunk_payloads)
            with param.parameterized.discard_events(self.model):
                self.model.chunk_payloads = [] # Clean up

        self.model.param.watch(fn, 'chunk_payloads')                             
    