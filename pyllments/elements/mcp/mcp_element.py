from typing import Union, Literal

import param
from pydantic import Field, create_model, RootModel, BaseModel
from loguru import logger

from pyllments.base.element_base import Element
from pyllments.payloads import SchemaPayload, StructuredPayload, ToolsResponsePayload
from pyllments.common.pydantic_models import CleanModel
from .mcp_model import MCPModel

# TODO: Consider the access rights and confirmation ability of the tool response payload
class MCPElement(Element):
    """An Element that handles tool calling with the Model Context Protocol."""

    _tools_schema = param.ClassSelector(default=None, class_=BaseModel, is_instance=False, doc="""
        The schema of the tools""")
    
    def __init__(self, **params):
        super().__init__(**params)
        self.model = MCPModel(**params)

        self._tools_schema_output_setup()
        self._tool_request_structured_input_setup()
        self._tool_response_output_setup()

        # self._tool_response_output_setup()
    
    def _tools_schema_output_setup(self):
        async def pack(tools_schema: type(BaseModel)) -> SchemaPayload:
            return SchemaPayload(schema=tools_schema)

        async def on_connect(port, input_port):
            await self.model.await_ready()
            self.logger.info(f"tools_schema_output connected, emitting schema: {self.tools_schema}")
            await port.stage_emit(tools_schema=self.tools_schema)

        tools_schema_output = self.ports.add_output(
            name='tools_schema_output',
            pack_payload_callback=pack,
            on_connect_callback=on_connect,
            readiness_check=self.model.await_ready)
        # Emits the tools schema when it changes - for updates
        # self.model.param.watch(
        #     lambda event: tools_schema_output.stage_emit(tools_schema=event.new),
        #     'tools'
        #     )
    
    def _tool_request_structured_input_setup(self):
        async def unpack(payload: StructuredPayload):
            tool_request_list = payload.model.data
            await self.ports.tool_response_output.stage_emit(tool_request_list=tool_request_list)

        self.ports.add_input(
            name='tool_request_structured_input',
            unpack_payload_callback=unpack,
            readiness_check=self.model.await_ready)

    def _tool_response_output_setup(self):
        """For the purpose of passing tools to LLMs (see litellm tool call format)"""
        async def pack(tool_request_list: list) -> ToolsResponsePayload:
            tool_responses = {}
            for tool_request in tool_request_list:
                hybrid_name = tool_request['name']
                parameters = tool_request.get('parameters', None)
                
                # Add error handling if the tool is not found in the dictionary
                if hybrid_name not in self.model.tools:
                    logger.error(f"Tool {hybrid_name} not found in tools")
                    continue
                    
                description = self.model.tools[hybrid_name]['description']
                # Include permission requirement flag in the payload
                permission_required = self.model.tools[hybrid_name].get('permission_required', False)
                tool_responses[hybrid_name] = {
                    'mcp_name': self.model.hybrid_name_mcp_tool_map[hybrid_name]['mcp_name'],
                    'tool_name': self.model.hybrid_name_mcp_tool_map[hybrid_name]['tool_name'],
                    'description': description,
                    'parameters': parameters,
                    'permission_required': permission_required,
                    'call': self.model.create_call(hybrid_name, parameters)
                }
            return ToolsResponsePayload(tool_responses=tool_responses)
            
        self.ports.add_output(name='tool_response_output', pack_payload_callback=pack)

    @property
    def tools_schema(self) -> BaseModel:
        if not self._tools_schema:
            self._tools_schema = self.create_tools_schema(self.model.tools)
        return self._tools_schema

    def create_tools_schema(self, tools_dict):
        tool_schema_list = []
        for tool_name, tool_data in tools_dict.items():
            tool_schema_list.append(self.create_tool_model(tool_name, tool_data))
        tool_array_anyoff_schema = create_model('tool_array', __base__=(RootModel[list[Union[*tool_schema_list]]], CleanModel))
        return tool_array_anyoff_schema

    def create_tool_model(self, tool_name, tool_data):
        model_args = {}
        model_args['name'] = (Literal[tool_name], ...)
        if properties := tool_data['parameters'].get('properties'):
            model_args['parameters'] = (object, Field(json_schema_extra=properties))
        model_args['__doc__'] = tool_data['description']
        model_args['__base__'] = CleanModel

        tool_model = create_model(
            tool_name,
            **model_args
        )
        return tool_model