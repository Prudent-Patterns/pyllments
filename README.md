# 🚧pyllments🚧 [Construction In Progress]

*Speedrun your Prototyping*

[Documentation](https://docs.pyllments.com/)

## Build Visual AI Workflows with Python
A batteries-included LLM workbench for helping you integrate complex LLM flows into your projects - built fully in and for Python.
* Rapid prototyping complex workflows
* GUI/Frontend generation(With [Panel](https://github.com/holoviz/panel) components)
* Simple API deployment(Using FastAPI + Optional serving with Uvicorn)


Pyllments is a Python library that empowers you to build rich, interactive applications powered by large language models. It provides a collection of modular **Elements**, each encapsulating its data, logic, and UI—that communicate through well-defined input and output ports. With simple flow-based programming, you can effortlessly compose, customize, and extend components to create everything from dynamic GUIs to scalable API-driven services.

It comes prepackaged with a set of parameterized application you can run immediately from the command line like so:
```bash
pyllments recipe run branch_chat --height 900 --width 700
```
[See Recipes Here](https://docs.pyllments.com/recipes/)

#### Elements:
* Easily integrate into your own projects
* Have front end components associated with them, which allows you to build your own composable GUIs to interact with your flows
* Can individually or in a flow be served as an API (with limitless endpoints at any given part of the flow)

## Chat App Example
### With history, a custom system prompt, and an interface.
![Chat Flow](https://github.com/Prudent-Patterns/pyllments/blob/main/docs/assets/introduction/intro_example_flow.jpg?raw=true)

**intro chat flow example video placeholder**

In this example, we'll build a simple chat application using four core Elements from the Pyllments library. Elements are modular components that handle specific functions and connect via ports to form a data flow graph.

1. **ChatInterfaceElement**  
   Manages the chat GUI, including the input box for typing messages, a send button, and a feed to display the conversation. It emits user messages and renders incoming responses.

2. **HistoryHandlerElement**  
   Maintains a running log of all messages (user and assistant) and tool responses. It can emit the current message history to be used as context for the LLM.

3. **ContextBuilderElement**  
   Combines multiple inputs into a structured list of messages for the LLM. This includes a predefined system prompt (e.g., setting the AI's personality), the conversation history, and the latest user query.

4. **LLMChatElement**  
   Connects to a Large Language Model (LLM) provider, sends the prepared message list, and generates a response. It also offers a selector to choose different models or providers.

Here's what happens step by step in the chat flow:

1. **User Input**: You type a message in the `ChatInterfaceElement` and click send. This creates a `MessagePayload` with your text and the role 'user'.  
2. **History Update**: Your message is sent via a port to the `HistoryHandlerElement`, which adds it to the conversation log.  
3. **Context Building**: The `ContextBuilderElement` receives your message and constructs the full context. It combines:  
   - A fixed system prompt (e.g., "You are Marvin, a Paranoid Android."),  
   - The message history from `HistoryHandlerElement` (if available, up to a token limit),  
   - Your latest query.  
4. **LLM Request**: This combined list is sent through a port to the `LLMChatElement`, which forwards it to the selected LLM (like OpenAI's GPT-4o-mini).  
5. **Response Handling**: The LLM's reply is packaged as a new `MessagePayload` with the role 'assistant' and sent back to the `ChatInterfaceElement` to be displayed in the chat feed.  
6. **History Update (Again)**: The assistant's response is also sent to the `HistoryHandlerElement`, updating the log for the next interaction.  
7. **Cycle Repeats**: The process loops for each new user message, building context anew each time.

**chat_flow.py**
```python
from pyllments import flow
from pyllments.elements import ChatInterfaceElement, LLMChatElement, HistoryHandlerElement

# Instantiate the elements
chat_interface_el = ChatInterfaceElement()
llm_chat_el = LLMChatElement()
history_handler_el = HistoryHandlerElement(history_token_limit=3000)
context_builder_el = ContextBuilderElement(
    input_map={
        'system_prompt_constant': {
            'role': "system",
            'message': "You are Marvin, a Paranoid Android."
        },
        'history': {'ports': [history_handler_el.ports.message_history_output]},
        'query': {'ports': [chat_interface_el.ports.user_message_output]},
    },
    emit_order=['system_prompt_constant', '[history]', 'query']
)
# Connect the elements
chat_interface_el.ports.user_message_output > history_handler_el.ports.message_input
context_builder_el.ports.messages_output > llm_chat_el.ports.messages_input
llm_chat_el.ports.message_output > chat_interface_el.ports.message_emit_input
chat_interface_el.ports.assistant_message_output > history_handler_el.ports.message_emit_input

# Create the visual elements and wrap with @flow decorator to serve with pyllments
@flow
def interface():
    width = 950
    height = 800
    interface_view = chat_interface_el.create_interface_view(width=int(width*.75))
    model_selector_view = llm_chat_el.create_model_selector_view(
        models=config.custom_models, 
        model=config.default_model
        )
    history_view = history_handler_el.create_context_view(width=int(width*.25))

    main_view = pn.Row(
        pn.Column(
            model_selector_view,
            pn.Spacer(height=10),
            interface_view,
        ),
        pn.Spacer(width=10),
        history_view,
        styles={'width': 'fit-content'},
        height=height
    )
    return main_view
```
**CLI Command**
```bash
pyllments serve chat_flow.py
```

For more in-depth material, check our [Getting Started Tutorial](https://docs.pyllments.com/getting_started/)


# Elements are building blocks with a consistent interface
https://github.com/user-attachments/assets/771c3063-f7a9-4322-a7f4-0d47c7f50ffa

# Elements can create and manage easily composable front-end components called Views
https://github.com/user-attachments/assets/8346a397-0308-4aa1-ac9b-5045b701c754

# Using their `Ports` interface, Elements can be connected in endless permutations.
https://github.com/user-attachments/assets/1693a11a-ccdb-477b-868a-e93c0de3f52a

# Attach API endpoints to any part of the flow
https://github.com/user-attachments/assets/13126317-859c-4eb9-9b11-4a24bc6d0f07



## Temp Instructions:
### Installation:
Clone:
```bash
git clone https://github.com/Prudent-Patterns/pyllments.git
```
Install from local dir:
```bash
pip install .
```
## Examples
### Simple Example of an Interface (With an API)
![image](https://github.com/user-attachments/assets/45ef66f4-ea2b-4660-9f85-fc9eb7aa97b3)
```python
# Run with `pyllments serve simple_flow.py --logging'
# Requires an .env file in the working dir with an OPENAI_API_KEY entry

from langchain_core.messages import HumanMessage

from pyllments.elements import ChatInterfaceElement, LLMChatElement, APIElement
from pyllments.payloads import MessagePayload
from pyllments import flow


chat_interface_el = ChatInterfaceElement()
llm_chat_el = LLMChatElement()

def request_output_fn(message: str, role: str) -> MessagePayload:
    return MessagePayload(message=HumanMessage(content=message), role=role)

async def get_streamed_message(payload):
    return await payload.model.streamed_message()

api_el = APIElement(
    endpoint='api',
    connected_input_map={
        'message_input': llm_chat_el.ports.output['message_output']
    },
    response_dict={
        'message_input': {
            'message': get_streamed_message,
            'role': 'role'
        }
    },
    request_output_fn=request_output_fn
)

chat_interface_el.ports.output['message_output'] > llm_chat_el.ports.input['messages_input']
llm_chat_el.ports.output['message_output'] > chat_interface_el.ports.input['message_input']
api_el.ports.output['api_output'] > chat_interface_el.ports.input['message_emit_input']

@flow
def create_pyllments_flow():
    return chat_interface_el.create_interface_view(feed_height=700, input_height=120, width=800)
```
Interact with the interface with an API from a script or an nb(or anywhere else):
```python
import requests
response = requests.post(
    'http://0.0.0.0:8000/api',
    json={
        'message': 'tell me a joke about flying corgis',
        'role': 'human'
    }
)
response.json()
```

### RAG Application
https://gist.github.com/DmitriyLeybel/8e8aa3cd10809f15a05b6b91451722af
![image](https://github.com/user-attachments/assets/2b061219-d21a-420f-967a-45eadc65bcad)

