# 🚧pyllments🚧 [Construction In Progress]

## Build Visual AI Workflows with Python
A batteries-included LLM workbench for helping you integrate complex LLM flows into your projects - built fully in and for Python.
* Rapid prototyping complex workflows
* GUI/Frontend generation(With [Panel](https://github.com/holoviz/panel) components)
* Simple API deployment(Using FastAPI + Optional serving with Uvicorn)


Extensibility, composability, and modularity are first-class citizens.

Comes with a wide set of self-contained components called **Elements**, which contain the business and display logic. For example: LLM Model, Chat Interface, Context Handler

They are extensible and modifiable with a clear and straight-forward interface.

Each element may contain collections of input and output ports which enable the flow of data between them. 


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

