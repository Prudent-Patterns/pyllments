import panel as pn
from dotenv import load_dotenv
import param

import sys
sys.path.append('..')

load_dotenv()

# Try to use --design-... variables first
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

# Icon asset loading
assets_map = {'assets': '/workspaces/pyllments/pyllments/assets'}
pn.config.css_files = ['assets/file_icons/tabler-icons-outline.min.css']


def serve(servable, **kwargs):
    return pn.serve(servable, static_dirs=assets_map, **kwargs)

from pyllments.elements.file_loader import FileLoaderElement

fl = FileLoaderElement()

file_loader_view = fl.create_file_loader_view(sizing_mode='fixed', width=300, height=400)
# file_input_view = fl.create_file_input_view(width=200, height=200)
# srv = pn.serve(file_input_view)
file_loader_view.servable()