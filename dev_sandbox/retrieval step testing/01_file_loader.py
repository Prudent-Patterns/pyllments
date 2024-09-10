import panel as pn
from dotenv import load_dotenv
import param

import sys
sys.path.append('../..')

load_dotenv()

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

from pyllments.elements.file_loader import FileLoaderElement
from pyllments.tests import TestElement

file_loader_element = FileLoaderElement(file_dir='loaded_files')

test_element = TestElement()

file_loader_element.ports.output['file_list_output'] > test_element.ports.input['test_input']

file_loader_view = file_loader_element.create_file_loader_view()
pn.Column(file_loader_view, height=600, width=300).servable()

