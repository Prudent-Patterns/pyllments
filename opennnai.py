import panel as pn
import time

pn.config.global_css = [
    """
@import url('https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap');
body {
    background-color: #0C1314;
}
"""
]

chat_column = pn.Column(height=200, width=400, scroll=True)

stylesheet = """
.bk-input-group {
    font-family: 'Ubuntu', sans-serif;
}
.bk-input {
    background-color: #111926;
    border: 1px solid #4B586C;
    color: #F4F6F8;
}
.bk-input::placeholder {
    color: #F4F6F890;
}
"""
style = {
    "--border-radius": "9px",
  #  "border": "1px solid",
    # "stroke": "4B586C",
}
chat_input = pn.chat.ChatAreaInput(
    placeholder='Type your message here...',
    stylesheets=[stylesheet],
    styles=style,
    rows=2,
    auto_grow=True)

button_stylesheet = """
.bk-btn {
    border-radius: 8px;
    background-color: #D33A4B;
    font-size: 20px;
}
.bk-btn.bk-btn-default {
    background-color: #D33A4B;
}

.bk-btn.bk-btn-default {
    background-color: #D33A4B;
}
/*
:host(.solid) .bk-btn.bk-btn-default {
    background-color: #D33A4B;
*/
    }


"""
button_style = {'--surface-color': '#D33A4B', '--surface-text-color': '#F4F6F8'}


send_button = pn.widgets.Button(icon='send-2',
                                stylesheets=[button_stylesheet],
                                styles=button_style)

def send_message(event):
    message = chat_input.value_input
    if message:
        message_pane = pn.Row(pn.pane.Markdown(message))
        chat_column.append(message_pane)
        time.sleep(0.25)
        for word in message.split():
            message_pane[0].object += word + " "
            time.sleep(0.01)  
        chat_input.value_input = ''  

send_button.on_click(send_message)
pn.Column(chat_column, pn.Row(chat_input, send_button)).servable()
