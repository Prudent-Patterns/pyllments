from typing import Union

import param

from pyllments.base.element_base import Element
from pyllments.elements.chunker.text_chunker_model import TextChunkerModel
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.file import FilePayload


class TextChunkerElement(Element):

    def __init__(self, **params):
        super().__init__(**params)
        self.model = TextChunkerModel(**params)
        
        self._file_input_setup()
        self._chunk_output_setup()

    def _file_input_setup(self):
        def unpack(payload: Union[FilePayload, list[FilePayload]]):
            file_payload_list = payload if isinstance(payload, list) else [payload]
            for file_payload in file_payload_list:
                chunks = self.model.make_chunks(file_payload)
                self.ports.output['chunk_output'].stage_emit(chunks=chunks)
                
        self.ports.add_input(name='file_input', unpack_payload_callback=unpack)

    def _chunk_output_setup(self):
        def pack(chunks: list[ChunkPayload]) -> list[ChunkPayload]:
            return chunks
        
        self.ports.add_output(name='chunk_output', pack_payload_callback=pack)