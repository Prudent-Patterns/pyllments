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
            },
            'news_mcp': {
                'mcp_name': 'news_mcp',
                'tool_name': 'latest_headlines',
                'description': 'Fetch the latest news headlines.',
                'parameters': {'category': 'technology'},
                'response': {
                    'meta': None,
                    'content': [{
                        'type': 'text',
                        'text': 'Latest technology news: AI is transforming industries.',
                        'annotations': None
                    }],
                    'isError': False
                }
            },
            'finance_mcp': {  # New MCP tool added
                'mcp_name': 'finance_mcp',
                'tool_name': 'stock_price',
                'description': 'Get the current stock price for a specified company.',
                'parameters': {'ticker': 'AAPL'},
                'response': {
                    'meta': None,
                    'content': [{
                        'type': 'text',
                        'text': 'The current stock price of Apple Inc. is $150, reflecting a steady increase over the past week as investor confidence grows in the company’s innovative product lineup and strong market performance.',
                        'annotations': None
                    }],
                    'isError': False
                }
            },
            'crypto_mcp': {  # New MCP tool for cryptocurrency
                'mcp_name': 'crypto_mcp',
                'tool_name': 'crypto_price',
                'description': 'Get the current price of a specified cryptocurrency.',
                'parameters': {'ticker': 'BTC'},
                'response': {
                    'meta': None,
                    'content': [{
                        'type': 'text',
                        'text': 'The current price of Bitcoin (BTC) is $40,000, showing a significant rise in the last 24 hours.',
                        'annotations': None
                    }],
                    'isError': False
                }
            },
            'sports_mcp': {  # New MCP tool for sports updates
                'mcp_name': 'sports_mcp',
                'tool_name': 'latest_scores',
                'description': 'Fetch the latest scores from ongoing sports events.',
                'parameters': {'sport': 'football'},
                'response': {
                    'meta': None,
                    'content': [{
                        'type': 'text',
                        'text': 'Latest scores: Team A 2 - 1 Team B. A thrilling match with a last-minute goal!',
                        'annotations': None
                    }],
                    'isError': False
                }
            }
        }
    )

    # message_payload = MessagePayload(
    #     role='user',
    #     content='What is the weather in San Francisco?',
    #     mode='atomic'
    # )

    # # pipe_el.ports.pipe_output > chat_el.ports.tools_response_input
    # pipe_el.ports.pipe_output > chat_el.ports.message_input

    # # pipe_el.send_payload(tool_response_payload)
    # pipe_el.send_payload(message_payload)
    chat_el.model.message_list.append(tool_response_payload)

    chat_interface_view = chat_el.create_interface_view(width=700, height=800)

    return chat_interface_view