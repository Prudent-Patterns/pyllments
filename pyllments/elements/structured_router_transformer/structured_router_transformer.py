import json
from os import name
from typing import Union, Literal
import asyncio

import param
from pydantic import BaseModel, create_model, RootModel
from loguru import logger

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.base.element_base import Element
from pyllments.common.pydantic_models import CleanModel
from pyllments.payloads import MessagePayload, SchemaPayload, StructuredPayload
from pyllments.ports import OutputPort

# TODO: add an ability to pass extra fields into any given route
# Use case: add a reason field which is used for sending a reason message back to the user
# when choosing a route or tools
class StructuredRouterTransformer(Element):
    """An Element that routes and transforms structured data based on a routing map.
    
    This element is designed to parse structured input from a MessagePayload (usually JSON),
    validate it against a generated Pydantic schema, and route the data to different output ports
    based on the 'route' field in the payload. It can also optionally transform the data
    before emitting it through the corresponding output port.
    
    The element works by:
    1. Creating a unified schema from sub-schemas defined in the routing_map
    2. Parsing incoming JSON messages against this schema
    3. Extracting the appropriate route and data
    4. Transforming the data if needed
    5. Emitting the data through the corresponding output port
    
    It can also receive schema updates through dedicated schema input ports.
  
    """
    routing_map = param.Dict(default={}, doc="""
        A dictionary defining the routing logic. Each key represents a route name.
        The value is a dictionary with the following keys:

        - 'schema': (dict) Defines the expected structure for this route.
            - Can contain 'pydantic_model': (type[BaseModel] | type) directly specifying the Pydantic model or basic type (e.g., str).
            - OR 'ports': (list[InputPort]) List of input ports to listen on for schema updates (e.g., from an MCPElement).
            - OR 'payload_type': (type[Payload]) Expected payload type carrying the schema on the input ports. Defaults to SchemaPayload if 'ports' is used.
            - 'extract_callback': (callable, optional) A function that takes the schema payload and returns the Pydantic model. Defaults to `lambda payload: payload.model.schema`.
            - 'name': (str, optional) A name used for this route in the combined Pydantic schema. Defaults to the route key.
        - 'payload_type': (type[Payload]) The type of Payload to emit from the output port associated with this route.
        - 'ports': (list[InputPort], optional) A list of input ports that the corresponding output port for this route should connect to.
        - 'transform': (callable, optional) A function to transform the extracted data before emitting it.
            - This function receives one argument: the data extracted from the input message that corresponds to this route's key.
              If the schema for the route defines a Pydantic `BaseModel`, the argument passed here will be the result of calling `.model_dump()` on that model instance (a dict).
              Otherwise, it's the raw extracted value (e.g., a string, list, etc.).
            - The function MUST return a Payload instance (matching the 'payload_type' defined for this route).
            - If omitted, the element defaults to creating a `StructuredPayload` where its `data` attribute is the extracted value.
        - 'content_callback': (callable, optional) Currently unused placeholder.

        Example:
        routing_map = {
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': MessagePayload,
                'ports': [chat_interface_el.ports.message_input] # Output connects here
            },
            'tools': {
                'schema': {
                    'ports': [mcp_el.ports.tools_schema_output], # Input schema from here
                    'name': 'tools_request' # Route named 'tools_request' in schema
                },
                'transform': lambda data_dict: ToolCallPayload(tools=data_dict['tools']), # Custom transform
                'payload_type': ToolCallPayload,
                'ports': [mcp_el.ports.tool_call_input] # Output connects here
            }
        }
        """)

    flow_controller = param.ClassSelector(class_=FlowController)

    incoming_output_port = param.ClassSelector(class_=OutputPort)

    pydantic_model = param.ClassSelector(default=None,
        class_=(BaseModel, RootModel), is_instance=False, doc="""
        The schema generated from the route subschemas.
        """)

    def __init__(self, **params):
        super().__init__(**params)

        self.routing_setup()
        self.ports = self.flow_controller.ports
        self.set_pydantic_schema()
        self.setup_schema_output()

    def routing_setup(self):
        flow_controller_kwargs = {}
        flow_controller_kwargs['flow_map'] = self.flow_map_setup()
        flow_controller_kwargs['flow_fn'] = self.flow_fn_setup()
        self.flow_controller = FlowController(**flow_controller_kwargs, containing_element=self)
        self.ports = self.flow_controller.ports

    def flow_map_setup(self):
        flow_map = {'input': {}, 'output': {}}
        for route, route_params in self.routing_map.items():
            if ports := route_params.get('ports', None):
                flow_map['output'][route] = {'ports': ports}
            elif payload_type := route_params.get('payload_type', None):
                flow_map['output'][route] = {'payload_type': payload_type}
            else:
                raise ValueError(f"No ports or payload_type provided for route {route}")
            
            schema_params = route_params['schema']
            input_key = route + '_schema_input'
            if 'ports' in schema_params:
                flow_map['input'][input_key] = {
                    'ports': schema_params['ports'], 
                    'persist': True,
                }
            elif 'payload_type' in schema_params:
                flow_map['input'][input_key] = {
                    'payload_type': schema_params['payload_type'], 
                    'persist': True,
                }
            elif 'pydantic_model' in schema_params:
                pass
            else:
                raise ValueError(f"No valid schema parameters provided for route {route}")
        if self.incoming_output_port and self.incoming_output_port.payload_type is MessagePayload:
            flow_map['input']['message_input'] = {'ports': [self.incoming_output_port]}
        else:
            flow_map['input']['message_input'] = {'payload_type': MessagePayload}
        return flow_map
    
    def setup_schema_output(self):
        async def pack(pydantic_model: type(RootModel)) -> SchemaPayload:
            return SchemaPayload(schema=pydantic_model)
        async def on_connect(output_port, new_input_port):
            return await output_port.stage_emit_to(
                new_input_port,
                pydantic_model=self.pydantic_model
            )
        self.ports.add_output(
            name='schema_output',
            pack_payload_callback=pack,
            on_connect_callback=on_connect
        )
        # Emits the schema payload when the pydantic model changes
        async def emit_on_change(event):
            self.logger.info(f"pydantic_model changed, emitting updated schema")
            await self.ports.schema_output.stage_emit(pydantic_model=event.new)
            
        self.param.watch(
            emit_on_change,
            'pydantic_model'
            )
        
    @property
    def schemas(self):
        """
        Used to get the schema and schema name to use for each of the routes.
        Only return the schemas that have pydantic models
        """
        schemas = {}
        for route in self.routing_map:
            if pydantic_model := self.routing_map[route]['schema'].get('pydantic_model', None):
                if self.routing_map[route]['schema'].get('name', None):
                    schema_name_str = self.routing_map[route]['schema']['name']
                else:
                    schema_name_str = route
                schemas[route] = {
                    'name': schema_name_str,
                    'pydantic_model': pydantic_model
                    }
        return schemas
    
    def set_pydantic_schema(self, pydantic_schema=None):
        """
        Creates the overarching Root Union schema based on the schemas in the routes. Titles stripped.
        One such route (reply can be a more complex nested object):
        {
            'route': 'reply',
            'reply': 'some reply'
        }
        """
        if pydantic_schema:
            self.pydantic_model = pydantic_schema
        else:
            sub_pydantic_models = []
            for schema in self.schemas.values():
                sub_pydantic_model_kwargs = {
                    'route': (Literal[schema['name']], ...), # Literal always required
                    schema['name']: (schema['pydantic_model'], ...),
                    '__base__': CleanModel
                    }
                sub_pydantic_model = create_model(f"{schema['name']}_route", **sub_pydantic_model_kwargs)
                sub_pydantic_models.append(sub_pydantic_model)
            self.pydantic_model = create_model(
                '',
                __base__=(RootModel[Union[*sub_pydantic_models]], CleanModel),
                )

    def flow_fn_setup(self):

        async def flow_fn(**kwargs):
            if (active := kwargs['active_input_port']).name == 'message_input':
                # route = active.name
                message_content = await active.payload.model.aget_message()
                self.logger.debug(f"Incoming JSON: {message_content}")
                
                # Handle empty message content
                if not message_content or message_content.strip() == "":
                    self.logger.error("Received empty message content")
                    return
                try:
                    model = self.pydantic_model.model_validate_json(message_content).root
                    self.logger.debug(f"Root model: {model}")
                    
                    route = model.route
                    if model.route not in self.routing_map:
                        raise ValueError(f"Route {model.route} not found in routing_map keys: {self.routing_map.keys()}")
                    output_model = getattr(model, route)
                    output_value = output_model.model_dump() if isinstance(output_model, BaseModel) else output_model
                    if transform := self.routing_map[route].get('transform', None):
                        output_payload = transform(output_value)
                    else: # Default to message payload
                        # json_str = output_model.model_dump_json()
                        output_payload = StructuredPayload(data=output_value)
                    await kwargs[route].emit(output_payload)
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    self.logger.error(f"Schema expected: {self.pydantic_model.model_json_schema()}")
                    # Optionally, you could add a default route or error handling here
            # Set the pydantic schema based on the provided schema input
            elif active.name.endswith('_schema_input'):
                route = active.name.removesuffix('_schema_input')
                if extract_callback := self.routing_map[route]['schema'].get('extract_callback', None):
                    pydantic_schema = extract_callback(active)
                else: # Assume schema payload
                    pydantic_schema = active.payload.model.schema
                self.routing_map[route]['schema']['pydantic_model'] = pydantic_schema
                self.set_pydantic_schema()
                self.logger.debug(f"Updated schema: {self.pydantic_model.model_json_schema()}")
        return flow_fn