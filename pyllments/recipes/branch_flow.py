"""
This recipe creates a branching chat interface with an LLM backend. The interface can be customized through various display parameters to match your application's needs.
"""
from dataclasses import dataclass, field
import re
from copy import copy
import uuid

import panel as pn

from pyllments import flow
from pyllments.elements import ChatInterfaceElement, LLMChatElement, HistoryHandlerElement

@dataclass
class Config:
    """
    
    """
    width: int = field(
        default=800,
        metadata={
            "help": "Overall width of the chat interface in pixels.",
            "min": 400
        }
    )
    height: int = field(
        default=720,
        metadata={
            "help": "Overall height of the chat interface in pixels.",
            "min": 400
        }
    )
    test_dict: dict = field(
        default_factory=dict,
        metadata={
            "help": "A test dictionary field",
        }
    )

print(config.test_dict)




class ChatFlowManager:
    """Manages chat flows and their lifecycle"""
    def __init__(self):
        self.flows = {}
        
    def create_flow(self, tab_name: str='New Chat', from_flow=None, branch=False):
        """
        Creates and stores a new chat flow
        Three Conditions:
        1. If from_flow is None and branch is False, create a new flow
        2. If from_flow is not None and branch is False, create a new flow from the existing flow without copying messages
        3. If from_flow is not None and branch is True, create a new flow from the existing flow and copy messages
        """        
        if (not from_flow or not branch):
            flow = {
                'chat_interface': ChatInterfaceElement(),
                'llm_chat': LLMChatElement(),
                'history_handler': HistoryHandlerElement(),
                'name': tab_name
            }
        elif from_flow and branch:
            flow = {}
            # set up chat_interface
            chat_interface_model_param_copies = self._model_param_copy(from_flow['chat_interface'].model)
            flow['chat_interface'] = ChatInterfaceElement(**chat_interface_model_param_copies)
            # set up history_handler
            history_handler_model_param_copies = self._model_param_copy(from_flow['history_handler'].model)
            flow['history_handler'] = HistoryHandlerElement(**history_handler_model_param_copies)
            # set up llm_chat
            llm_chat_model_param_copies = self._model_param_copy(from_flow['llm_chat'].model)
            flow['llm_chat'] = LLMChatElement(**llm_chat_model_param_copies)

            flow['name'] = tab_name
        
        # Connect the elements
        flow['chat_interface'].ports.output['message_output'] > flow['history_handler'].ports.input['message_input']
        flow['history_handler'].ports.output['messages_output'] > flow['llm_chat'].ports.input['messages_input']
        flow['llm_chat'].ports.output['message_output'] > flow['chat_interface'].ports.input['message_input']
        flow['llm_chat'].ports.output['message_output'] > flow['history_handler'].ports.input['messages_input']
        # Create view with unique name
        interface_view = flow['chat_interface'].create_interface_view(
            input_height=110,
            sizing_mode='stretch_both'
        )
        if from_flow:
            provider_val = from_flow['llm_chat'].model_selector_view[0].value
            model_val = from_flow['llm_chat'].model_selector_view[2].value
            model_selector_view = flow['llm_chat'].create_model_selector_view(provider=provider_val, model=model_val)
        else:
            model_selector_view = flow['llm_chat'].create_model_selector_view()
            
        view = pn.Column(model_selector_view, pn.Spacer(height=10), interface_view, name=tab_name)
        view.uuid = uuid.uuid4()  # Add UUID as attribute for identification
        
        self.flows[view.uuid] = flow
        return flow, view
    
    def remove_flow(self, view_id: str):
        """Cleans up and removes a flow"""
        if view_id in self.flows:
            del self.flows[view_id]
            
    def _model_param_copy(self, model):
        """Copies a model's parameters for insertion into a new element"""
        return {k: copy(v) for k, v in model.param.values().items()}

tabs_stylesheet = """
:host(.bk-left) {
    .bk-tab {
        overflow: hidden;
        border-width: 1px;
        padding-left: 10px;
        border-radius: var(--radius);
        border-color: transparent; 
        display: flex;
        justify-content: space-between;
        &:hover {
            border-color: var(--secondary-accent-color); 
            background-color: var(--primary-background-color); /* Keep primary background color on hover */
        }
    }

    .bk-header {
        width: 160px;
        background-color: var(--secondary-background-color); 
        margin-right: 10px; 
        border-radius: var(--radius);  
        border-color: var(--light-outline-color);
    }

    .bk-tab.bk-active {
        border-color: var(--light-outline-color); /* Keep light outline color for active tab */
        color: var(--white);
        background-color: var(--light-outline-color);  /* Active tab should have light outline color */
        
        &:hover {
            background-color: var(--light-outline-color); /* Keep light outline color on hover for active tab */
            border-color: var(--secondary-accent-color); /* Maintain light outline color on hover for active tab */
        }
    }
}

.bk-close {
    background-color: var(--faded-text-color);
    width: 16px;
    height: 16px;
    
    &:hover {
        background-color: var(--primary-accent-color);
    }
}

"""
tab_input_stylesheet = """
:host {
    .bk-input {
        background-color: var(--light-outline-color);
        border: 1px solid var(--faded-text-color);
        color: var(--white);
    }
    .bk-input:focus {
        border-color: var(--tertiary-accent-color);
    }
    .bk-input::placeholder {
        color: var(--primary-background-color);
        font-size: 1.2em;
        font-weight: 400;
    }
}
"""

branch_button_stylesheet = """
:host {
    --surface-color: var(--primary-accent-color);
    --surface-text-color: var(--white);

    .bk-btn {
        font-size: 18px;
    }
}
"""

chat_button_stylesheet = """
:host {
    --surface-color: var(--primary-accent-color);
    --surface-text-color: var(--white);

    .bk-btn {
        font-size: 18px;
    }
}
"""
tab_row_stylesheet = """
:host {
    border-style: solid;
    border-color: var(--light-outline-color);
    border-width: 1px;
    border-radius: var(--radius);
    padding-bottom: 5px;
    padding-top: 5px;
}
"""

@flow
def create_branching_app():
    # Initialize flow manager
    flow_manager = ChatFlowManager()

    # Create initial flow
    initial_tab_name = 'Initial Chat'
    initial_flow, initial_view = flow_manager.create_flow(initial_tab_name)

    # Setup new branch creation UI
    new_tab_name_input = pn.widgets.TextInput(
        placeholder='Enter the new chat/branch name',
        stylesheets=[tab_input_stylesheet],
        height=42
    )
    new_branch_button = pn.widgets.Button(name='New Branch', icon='hexagon-plus', height=42,stylesheets=[branch_button_stylesheet])
    new_chat_button = pn.widgets.Button(name='New Chat', icon='hexagon-plus', height=42,stylesheets=[chat_button_stylesheet])
    # 64px height of the row
    new_tab_row = pn.Row(new_tab_name_input, new_chat_button,new_branch_button, stylesheets=[tab_row_stylesheet])

    # Initialize tabs with first chat
    tabs = pn.Tabs(
        (initial_tab_name, initial_view),
        closable=True,
        tabs_location='left',
        stylesheets=[tabs_stylesheet]
    )

    def create_new_tab(event):
        # Get current active flow using Column's uuid
        active_tab_view = tabs[tabs.active]
        active_flow = flow_manager.flows.get(active_tab_view.uuid)

        new_tab_name = new_tab_name_input.value

        def extract_number_from_end(s):
            match = re.search(r'(.*?)(\d+)$', s)
            if match:
                prior = match.group(1) or None
                num = int(match.group(2))
                return {'prior': prior, 'num': num}
            return {'prior': s, 'num': False}

        if event.obj is new_branch_button:
            if active_flow:
                if not new_tab_name or new_tab_name.strip() == "":
                    if number := extract_number_from_end(active_tab_view.name)['num']:
                        new_tab_name = f"{extract_number_from_end(active_tab_view.name)['prior']} {number + 1}"
                    else:
                        new_tab_name = f"{active_tab_view.name} 1"
                new_flow, new_view = flow_manager.create_flow(new_tab_name, from_flow=active_flow, branch=True)
            else:
                new_flow, new_view = flow_manager.create_flow(new_tab_name)

        elif event.obj is new_chat_button or event.obj is new_tab_name_input:
            if active_flow:
                if not new_tab_name:
                    new_tab_name = 'New Chat'
                new_flow, new_view = flow_manager.create_flow(new_tab_name, from_flow=active_flow, branch=False)
            else:
                new_flow, new_view = flow_manager.create_flow(new_tab_name)
        
        # Add new tab
        tabs.append((new_tab_name, new_view))
        new_tab_name_input.value = ''
        tabs.active = len(tabs) - 1

    def handle_tabs_change(event):
        """Handle tab closures by cleaning up associated flows"""
        if event.name == 'objects' and len(event.new) < len(event.old):  # Only handle removals
            current_view_ids = {getattr(obj[0], 'uuid', None) for obj in event.new}
            
            # Find and remove flows whose views are no longer in the tabs
            for view_id in list(flow_manager.flows.keys()):
                if view_id not in current_view_ids:
                    flow_manager.remove_flow(view_id)

    # Connect event handlers
    new_tab_name_input.param.watch(create_new_tab, 'enter_pressed')
    new_branch_button.on_click(create_new_tab)
    new_chat_button.on_click(create_new_tab)
    tabs.param.watch(handle_tabs_change, 'objects')

    # Create main layout
    return pn.Column(new_tab_row, pn.Spacer(height=10), tabs, width=config.width, height=config.height)