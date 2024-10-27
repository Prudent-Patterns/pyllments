import sys
sys.path.append('../..')

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import panel as pn
from panel.io.fastapi import add_application

from pyllments.logging import setup_logging
from pyllments.elements.chat_interface import ChatInterfaceElement
from pyllments.elements.llm_chat import LLMChatElement


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
load_dotenv()

chat_interface_element = ChatInterfaceElement()
llm_chat_element = LLMChatElement()

chat_interface_element.ports.output['message_output'] > llm_chat_element.ports.input['messages_input']
llm_chat_element.ports.output['message_output'] > chat_interface_element.ports.input['message_input']

app = FastAPI()
app.mount('/assets', StaticFiles(directory='/workspaces/pyllments/pyllments/assets'), name='assets')

@add_application('/', app=app, title='Pyllments')
def create_pyllments_app():
    return chat_interface_element.create_interface_view(feed_height=500, input_height=150, width=500)