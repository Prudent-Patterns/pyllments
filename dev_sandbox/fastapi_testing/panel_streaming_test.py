import panel as pn
import time


def generate_text():
    text = "This is some text I am generating, it ain't much but it's honest work"
    text_list = text.split() 
    for word in text_list:
        yield word + " "  
        time.sleep(0.1)

button = pn.widgets.Button(name='Click me pls')
md = pn.pane.Markdown('Placeholder Text')

def update_md(event):
    md.object = ''
    for word in generate_text():
        md.object += word

button.on_click(update_md)

pn.Column(button, md).servable()

    