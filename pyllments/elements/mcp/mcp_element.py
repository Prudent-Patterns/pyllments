from typing import Union, Literal

import param
from pydantic import Field, create_model, RootModel, BaseModel

from pyllments.base.element_base import Element
from pyllments.payloads import SchemaPayload, StructuredPayload
from pyllments.common.pydantic_models import CleanModel
from .mcp_model import MCPModel


class MCPElement(Element):
    """An Element that handles tool calling with the Model Context Protocol."""
    _tool_list_schema = param.ClassSelector(default=None, class_=BaseModel, is_instance=False, doc="""
        The schema of the tool list
        """)
    def __init__(self, **params):
        super().__init__(**params)
        self.model = MCPModel(**params)


        self._tool_list_schema_output_setup()
        self._tool_list_structured_output_setup()
        # self._tool_response_output_setup()
        # self._tool_call_input_setup()
    
    def _tool_list_schema_output_setup(self):
        def pack(tool_list: type(BaseModel)) -> SchemaPayload:
            return SchemaPayload(schema=self.tool_list_schema)

        tool_list_schema_output = self.ports.add_output(
            name='tool_list_schema_output',
            pack_payload_callback=pack,
            on_connect_callback=lambda port: port.stage_emit(tool_list=self.tool_list_schema))
        # Emits the tool_list when it changes - for updates
        self.model.param.watch(
            lambda event: tool_list_schema_output.stage_emit(tool_list=event.new),
            'tool_list'
            )

    def _tool_list_structured_output_setup(self):
        """For the purpose of passing tools to LLMs (see litellm tool call format)"""
        pass

    @property
    def tool_list_schema(self) -> BaseModel:
        if not self._tool_list_schema:
            self._tool_list_schema = self.create_tools_schema(self.model.tool_list)
        return self._tool_list_schema

    def create_tools_schema(self, tool_list):
        tool_schema_list = [self.create_tool_model(tool) for tool in tool_list]
        tool_array_anyoff_schema = create_model('tool_array', __base__=(RootModel[list[Union[*tool_schema_list]]], CleanModel))
        return tool_array_anyoff_schema

    def create_tool_model(self, tool):
        model_args = {}
        model_args['name'] = (Literal[tool['name']], ...)
        if properties := tool['parameters'].get('properties'):
            model_args['parameters'] = (object, Field(json_schema_extra=properties))
        model_args['__doc__'] = tool['description']
        model_args['__base__'] = CleanModel


        tool_model = create_model(
            tool['name'],
            **model_args
        )
        return tool_model


