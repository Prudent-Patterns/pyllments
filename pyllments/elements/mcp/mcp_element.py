import param

from pyllments.base.element_base import Element
from pyllments.payloads import ToolListPayload, ToolCallPayload, ToolResponsePayload
from .mcp_model import MCPModel

class MCPElement(Element):
    """An Element that handles tool calling with the Model Context Protocol."""
    def __init__(self, **params):
        super().__init__(**params)
        self.model = MCPModel(**params)

        self._tool_list_output_setup()
        self._tool_response_output_setup()
        self._tool_call_input_setup()
    
    def _tool_list_output_setup(self):
        def pack(tool_list: ToolListPayload) -> ToolListPayload:
            return tool_list

        tool_list_output = self.ports.add_output(
            name='tool_list_output',
            pack_payload_callback=pack,
            on_connect_callback=lambda port: port.stage_emit(tool_list=self.model.tool_list))
        # Emits the tool_list when it changes - for updates
        self.model.param.watch(
            lambda event: tool_list_output.stage_emit(tool_list=event.new),
            'tool_list'
            )
            