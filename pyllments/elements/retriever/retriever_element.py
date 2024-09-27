
from typing import Union
from pyllments.base.element_base import Element
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload
from pyllments.elements.retriever.retriever_model import RetrieverModel

class RetrieverElement(Element):
    # Needs two col viz, one for the created chunks, and one for the retrieved chunks

    def __init__(self, **params):
        super().__init__(**params)
        self.model = RetrieverModel(**params)

        self._chunk_input_setup()
        self._message_query_input_setup()
        self._chunk_result_output_setup()

    def _chunk_input_setup(self):
        """For the collection populating process"""
        def unpack(payload: Union[ChunkPayload, list[ChunkPayload]]):
            chunks = payload if isinstance(payload, list) else [payload]
            for chunk in chunks:
                self.model.add_item(chunk)
        
        self.ports.add_input('chunk_input', unpack)

    def _message_query_input_setup(self):
        """The input query used for retrieval"""
        def unpack(payload: MessagePayload):
            chunks = self.model.retrieve(payload)
            self.ports.output['chunk_output'].stage_emit(chunk_payload=chunks)
        
        self.ports.add_input('message_input', unpack)

    def _chunk_result_output_setup(self):
        """The output of the retrieval process"""
        def pack(chunk_payload: list[ChunkPayload]) -> list[ChunkPayload]:
            return chunk_payload
        
        self.ports.add_output('chunk_output', pack)