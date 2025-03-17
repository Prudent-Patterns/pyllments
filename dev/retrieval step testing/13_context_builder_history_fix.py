import panel as pn
from panel.io.fastapi import add_application
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


from dotenv import load_dotenv

import sys
sys.path.append('../..')

load_dotenv('/workspaces/pyllments/.env')

from pyllments.logging import setup_logging

setup_logging(log_file='file_loader.log', stdout_log_level='INFO', file_log_level='INFO')

pn.config.css_files = ['assets/file_icons/tabler-icons-outline.min.css']
pn.config.global_css = [
    """
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:ital,wght@0,100..900;1,100..900&family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap');
body {
    --primary-background-color: #0C1314;
    --secondary-background-color: #111926;
    --light-outline-color: #455368;
    --primary-accent-color: #D33A4B;
    --secondary-accent-color: #EDB737;
    --tertiary-accent-color: #12B86C;
    --white: #F4F6F8;
    --black: #353839;
    --faded-text-color: #6083B8;

    --base-font: 'Hanken Grotesk', sans-serif;
    --bokeh-base-font: 'Hanken Grotesk', sans-serif;
    --bokeh-font-size: 16px;
    --line-height: 1.55;
    --design-background-text-color: var(--white);

    
    background-color: var(--primary-background-color);
    /* Centering Body */
    display: flex;
    justify-content: center;
    align-items: center;
}
"""
]
from pyllments.elements.chunker import TextChunkerElement
from pyllments.elements.embedder import EmbedderElement
from pyllments.elements.file_loader import FileLoaderElement
from pyllments.elements.retriever import RetrieverElement
from pyllments.elements.chat_interface import ChatInterfaceElement
from pyllments.elements.context_builder import ContextBuilderElement
from pyllments.elements.flow_control.flow_controllers.switch.switch import Switch
from pyllments.payloads.message import MessagePayload
from pyllments.elements.history_handler import HistoryHandlerElement
from pyllments.elements.llm_chat import LLMChatElement
from pyllments.elements.api import APIElement
from pyllments.tests import TestElement

from langchain_core.messages import HumanMessage
import time
import asyncio

app = FastAPI()
app.mount('/assets', StaticFiles(directory='/workspaces/pyllments/pyllments/assets'), name='assets')

@add_application('/', app=app, title='Pyllments')
def create_pyllments_app():

    file_loader_element = FileLoaderElement(file_dir='loaded_files')
    chunker_element = TextChunkerElement(chunk_size=200, chunk_overlap=20)
    embedder_element = EmbedderElement()
    retriever_element = RetrieverElement()
    chat_interface_element = ChatInterfaceElement()
    llm_chat_element = LLMChatElement()

    test_element = TestElement(
        # receive_callback=lambda p: [i.model.message.content for i in p]
        receive_callback=lambda p: [i.model.text for i in p]
    )


    file_loader_element.ports.output['file_list_output'] > chunker_element.ports.input['file_input']
    chunker_element.ports.output['chunk_output'] > embedder_element.ports.input['chunk_input']
    embedder_element.ports.output['processed_chunks_output'] > retriever_element.ports.input['chunk_input']



    switch_element = Switch(
        payload_type=MessagePayload, 
        outputs=['with_retrieval', 'without_retrieval'], 
        current_output='without_retrieval'
    )

    chat_interface_element.ports.output['message_output'] > switch_element.ports.input['payload_input']
    embedder_element.ports.output['processed_message_output'] > retriever_element.ports.input['message_input']

    switch_element.ports.output['with_retrieval'] > embedder_element.ports.input['message_input']
    # retriever_element.ports.input['message_input']
    # embedder_element.ports.output['processed_message_output'] > context_builder.ports.input['query']

    history_handler_element = HistoryHandlerElement()
    test_element.ports.output['test_output'] > history_handler_element.ports.input['message_input']

    context_builder = ContextBuilderElement(
        connected_input_map={
            'main_system_prompt': ('system', 'You are a chatbot made for RAG. You will be given a history of previous messages, retrieved chunks of text, and a user query.'),
            'system_history_prompt': ('system', 'Below is the history of the conversation.'),
            'history': ('system', history_handler_element.ports.output['messages_output']),
            'system_retrieval_prompt': (
                'system', 
                'Below is the retrieved context for the conversation.'
            ),
            'retrieved': ('system', retriever_element.ports.output['chunk_output']),
            'system_query_prompt': (
                'system', 
                "Following, is the user query which you should respond to to the best of your ability given the information you have."
            ),
            'query': ('human', [embedder_element.ports.output['processed_message_output'], switch_element.ports.output['without_retrieval']])
        },
        build_map={
             'query': [
                'main_system_prompt',
                'system_query_prompt',
                'query'
            ],
            # When history exists
            'history': [
                'main_system_prompt', 
                'system_history_prompt', 
                'history', 
                'system_query_prompt',
                'query'
            ],
            # When history exists and retrieval is needed
            'retrieved': [
                'main_system_prompt', 
                'system_history_prompt', 
                'history', 
                'system_retrieval_prompt', 
                'retrieved', 
                'system_query_prompt',
                'query'
            ]
        }
    )

    context_builder.ports.output['messages_output'] > history_handler_element.ports.input['messages_input']
    context_builder.ports.output['messages_output'] > llm_chat_element.ports.input['messages_input']
    llm_chat_element.ports.output['message_output'] > history_handler_element.ports.input['message_input']
    llm_chat_element.ports.output['message_output'] > chat_interface_element.ports.input['message_input']
    # llm_chat_element.ports.output['message_output'] > test_element.ports.input['test_input']
    # context_builder.ports.output['messages_output'] >  test_element.ports.input['test_input']
    retriever_element.ports.output['chunk_output'] > test_element.ports.input['test_input']
    # embedder_element.ports.output['processed_chunks_output'] > test_element.ports.input['test_input']

    from langchain_core.messages import HumanMessage
    test_element.send_payload(MessagePayload(message=HumanMessage(content='Hello')))

    file_loader_view = file_loader_element.create_file_loader_view()
    chat_interface_view = chat_interface_element.create_interface_view(feed_height=500, input_height=150)
    switch_view = switch_element.create_switch_view(orientation='horizontal')

    def output_pack_fn(request_dict) -> MessagePayload:
        return MessagePayload(**{
            'message': HumanMessage(content=request_dict['message']),
            'role': request_dict['role']
        })
    
    async def message_callback(payload):
        while not payload.model.streamed:
            await asyncio.sleep(0.1)
        return payload.model.message.content
    api_element = APIElement(
        app=app,
        endpoint='api',
        connected_input_map={
            'message_input': llm_chat_element.ports.output['message_output']
        },
        response_dict={
            'message_input': {
                'message': message_callback,
                'role': 'role'
            }
        },
        output_pack_fn=output_pack_fn, 
        outgoing_input_port=chat_interface_element.ports.input['message_emit_input']
    )
    
    return pn.Row(
        pn.Column(
            retriever_element.create_created_chunks_view(height=445),
            pn.VSpacer(),
            retriever_element.create_retrieved_chunks_view(height=445),
            height=900,
            width=500
        ),
        pn.Spacer(width=10),
        pn.Column(
            file_loader_view, 
            pn.Spacer(height=10),
            chat_interface_view, 
            pn.Spacer(height=10),
            switch_view, 
            height=900, 
            width=500
        ),
        pn.Spacer(width=10),
        history_handler_element.create_context_view(height=900, width=500),
    )

# panel serve 10_retrieval_flow.py --static-dirs assets=/workspaces/pyllments/pyllments/assets