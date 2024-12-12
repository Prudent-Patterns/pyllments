from fastapi import FastAPI
from panel.io.fastapi import add_application
import panel as pn

import time

app = FastAPI()

@add_application('/', app=app, title='Pyllments')
def create_pyllments_app():
    def generate_text():
    # async def generate_text():
        text = "This is some text I am generating, it ain't much but it's honest work"
        text_list = text.split() 
        for word in text_list:
            yield word + " " 
            time.sleep(0.1)
            # await asyncio.sleep(0.1)

    button = pn.widgets.Button(name='Click me pls')
    md = pn.pane.Markdown('Placeholder Text')

    async def update_md(event):
        md.object = ''
        # async for word in generate_text():
        for word in generate_text():
            md.object += word

    button.on_click(update_md)

    return pn.Column(button, md)   
