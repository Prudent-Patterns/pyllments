from pyllments.elements import ChatInterfaceElement, PipeElement
from pyllments.serve import flow
from pyllments.payloads import ToolsResponsePayload, MessagePayload



@flow
def create_gui():
    chat_el = ChatInterfaceElement()
    pipe_el = PipeElement()
    
    # Create an instance of ToolResponsePayload with an example tool response
    tool_response_payload = ToolsResponsePayload(
        tool_responses={
            'weather_mcp': {
                'mcp_name': 'weather_mcp',
                'tool_name': 'temp',
                'description': 'Get the current weather for a specified location.',
                'parameters': {'location': 'San Francisco'},
                'response': {
                    'meta': None,
                    'content': [{
                        'type': 'text',
                        'text': 'The temperature is 54F.',
                        'annotations': None
                    }],
                    'isError': False
                }
            }
        }
    )
    message_payload = MessagePayload(
        role='user',
        content='What is the weather in San Francisco?',
        mode='atomic'
    )

    # # pipe_el.ports.pipe_output > chat_el.ports.tools_response_input
    # pipe_el.ports.pipe_output > chat_el.ports.message_input

    # # pipe_el.send_payload(tool_response_payload)
    # pipe_el.send_payload(message_payload)
    chat_el.model.message_list.append(tool_response_payload)

    chat_interface_view = chat_el.create_interface_view(width=700, height=800)

    return chat_interface_view