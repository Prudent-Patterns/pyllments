import time
from loguru import logger
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
            start_time = time.time()
            logger.info("RetrieverElement: Starting chunk input processing")
            chunks = payload if isinstance(payload, list) else [payload]
            for i, chunk in enumerate(chunks):
                self.model.add_item(chunk)
                if i % 100 == 0:  # Log every 100 chunks
                    logger.info(f"RetrieverElement: Processed {i+1} chunks. Time elapsed: {time.time() - start_time:.2f} seconds")
            logger.info(f"RetrieverElement: Finished processing {len(chunks)} chunks. Total time: {time.time() - start_time:.2f} seconds")
        
        self.ports.add_input('chunk_input', unpack)

    def _message_query_input_setup(self):
        """The input query used for retrieval"""
        def unpack(payload: MessagePayload):
            start_time = time.time()
            logger.info("RetrieverElement: Starting retrieval process")
            chunks = self.model.retrieve(payload)
            logger.info(f"RetrieverElement: Retrieval completed. Time elapsed: {time.time() - start_time:.2f} seconds")
            if chunks:
                self.ports.output['chunk_output'].stage_emit(chunk_payload=chunks)
                logger.info(f"RetrieverElement: Chunks staged for emission. Time elapsed: {time.time() - start_time:.2f} seconds")
        
        self.ports.add_input('message_input', unpack)

    def _chunk_result_output_setup(self):
        """The output of the retrieval process"""
        def pack(chunk_payload: list[ChunkPayload]) -> list[ChunkPayload]:
            return chunk_payload
        
        self.ports.add_output('chunk_output', pack)