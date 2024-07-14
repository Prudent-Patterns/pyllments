import panel as pn
import time

chat_column = pn.Column(height=200, width=400, scroll=True)
chat_input = pn.widgets.TextInput(placeholder='Type your message here...')
send_button = pn.widgets.Button(name='Send', button_type='primary')

def send_message(event):
    message = chat_input.value
    if message:
        message_pane = pn.pane.Markdown(
            '',
            stylesheets=["""
                :host {
                    max-height: none;
                }
                """])
        chat_column.append(message_pane)
        for word in message.split():
            message_pane.object += word + " "
            time.sleep(0.01)  
        chat_input.value = ''  

send_button.on_click(send_message)
pn.Column(chat_column, pn.Row(chat_input, send_button)).servable()

