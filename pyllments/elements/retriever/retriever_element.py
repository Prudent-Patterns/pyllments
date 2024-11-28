import time
from typing import Union

from loguru import logger
import panel as pn
import param

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload
from pyllments.elements.retriever.retriever_model import RetrieverModel

class RetrieverElement(Element):
    retrieved_chunks_view = param.ClassSelector(class_=pn.Column)
    created_chunks_view = param.ClassSelector(class_=pn.Column)

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
            self.model.add_items(chunks)  # Use add_items to process all chunks at once
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

    @Component.view
    def create_retrieved_chunks_view(
        self, 
        column_css: list = [],
        container_css: list = [],
        title_css: list = [],
        width: int = None,
        height: int = None,
        sizing_mode: str = 'stretch_both',
        title_visible: bool = True
    ) -> pn.Column:
        """Creates a view for displaying the retrieved chunks."""
        self.retrieved_chunks_container = pn.Column(*[
                chunk.create_collapsible_view()
                for chunk in self.model.retrieved_chunks
            ],
            scroll=True,
            sizing_mode='stretch_both',
            stylesheets=container_css
        )
        
        match (width, height):
            case (None, None):
                pass
            case (_, None):
                sizing_mode = 'stretch_height'
            case (None, _):
                sizing_mode = 'stretch_width'
            case (_, _):
                sizing_mode = 'fixed'
            
        self.retrieved_chunks_view = pn.Column(
            pn.pane.Markdown(
                "### Retrieved Chunks", 
                visible=title_visible,
                stylesheets=title_css,
                sizing_mode='stretch_width'
            ),
            self.retrieved_chunks_container,
            stylesheets=column_css,
            width=width,
            height=height,
            sizing_mode=sizing_mode,
            scroll=False
        )
        
        def _update_retrieved_chunks_view(event):
            self.retrieved_chunks_container.objects = [
                chunk.create_collapsible_view()
                for chunk in self.model.retrieved_chunks
            ]
            self.retrieved_chunks_view.param.trigger('objects')
        
        self.model.param.watch(_update_retrieved_chunks_view, 'retrieved_chunks')
        return self.retrieved_chunks_view

    @Component.view
    def create_created_chunks_view(
        self, 
        column_css: list = [],
        container_css: list = [],
        title_css: list = [],
        width: int = None,
        height: int = None,
        sizing_mode: str = 'stretch_both',
        title_visible: bool = True
    ) -> pn.Column:
        """Creates a view for displaying the created chunks."""
        self.created_chunks_container = pn.Column(*[
                chunk.create_collapsible_view()
                for chunk in self.model.created_chunks
            ],
            scroll=True,
            sizing_mode='stretch_both',
            stylesheets=container_css
        )
        match (width, height):
            case (None, None):
                pass
            case (_, None):
                sizing_mode = 'stretch_height'
            case (None, _):
                sizing_mode = 'stretch_width'
            case (_, _):
                sizing_mode = 'fixed'
        self.created_chunks_view = pn.Column(
            pn.pane.Markdown(
                "### Created Chunks", 
                visible=title_visible,
                stylesheets=title_css,
                sizing_mode='stretch_width'
            ),
            self.created_chunks_container,
            stylesheets=column_css,
            width=width,
            height=height,
            sizing_mode=sizing_mode,
            scroll=False
        )
        
        def _update_created_chunks_view(event):
            self.created_chunks_container.objects = [
                chunk.create_collapsible_view()
                for chunk in self.model.created_chunks
            ]
            self.created_chunks_view.param.trigger('objects')
        
        self.model.param.watch(_update_created_chunks_view, 'created_chunks')

        return self.created_chunks_view