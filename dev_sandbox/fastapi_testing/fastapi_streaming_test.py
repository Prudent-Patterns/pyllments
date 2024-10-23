from fastapi import FastAPI
from panel.io.fastapi import add_application
from fastapi.staticfiles import StaticFiles
import panel as pn
import time
import asyncio

app = FastAPI()
# app.mount('/assets', StaticFiles(directory='/workspaces/pyllments/pyllments/assets'), name='assets')

@add_application('/', app=app, title='Pyllments')
def create_pyllments_app():
    async def generate_text():
        text = "This is some text I am generating, it ain't much but it's honest work"
        text_list = text.split()  # Correctly split the text into words
        for word in text_list:
            yield word + " "  # Add a space after each word
            await asyncio.sleep(0.1)

    button = pn.widgets.Button(name='Click me pls')
    md = pn.pane.Markdown('Placeholder Text')

    async def update_md(event):
        md.object = ''  # Reset the markdown content
        async for word in generate_text():
            md.object += word

    button.on_click(update_md)

    return pn.Column(button, md)

    
