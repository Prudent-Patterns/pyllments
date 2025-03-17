import json
from typing import Union

import param
from pydantic import BaseModel, create_model, RootModel

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.base.element_base import Element
from pyllments.payloads import MessagePayload
from pyllments.ports import OutputPort


class StructuredRouterTransformer(Element):
    routing_map = param.Dict(default={}, doc="""
        routing_map = {
            'reply': {
                'schema': {'pydantic_model': RootModel[str]},
                'payload_type': MessagePayload,
                             
            'tools': {
                'schema': {
                    'ports': [mcp_el.ports.tool_list_schema_output],
                    'extract_callback': lambda payload: payload.model.schema
                    'name': 'tools' # Default name is the key in the routing_map
                },
                'transform': lambda pydantic_model: ToolCallPayload(tools=pydantic_model.tools),
                'ports': [mcp_el.ports.tool_call_input]
                'content_callback': lambda payload: payload.model.content
            }
        }
        """)

    flow_controller = param.ClassSelector(class_=FlowController)

    incoming_output_port = param.ClassSelector(class_=OutputPort)

    pydantic_model = param.ClassSelector(class_=BaseModel)

    def __init__(self, **params):
        super().__init__(**params)

        self.routing_setup()
        self.setup_schema_message_output()

    def routing_setup(self):
        flow_controller_kwargs = {}
        flow_controller_kwargs['flow_map'] = self.flow_map_setup()
        flow_controller_kwargs['flow_fn'] = self.flow_fn_setup()
        self.flow_controller = FlowController(**flow_controller_kwargs)
        self.ports = self.flow_controller.ports

    def flow_map_setup(self):
        flow_map = {'input': {}, 'output': {}}
        for route, route_params in self.routing_map.items():
            try:
                if 'ports' in route_params:
                    flow_map['output'][route] = route_params['ports']
                else:
                    flow_map['output'][route] = route_params['payload_type']
            except KeyError:
                raise ValueError(f"No ports or payload_type provided for route {route}")
            try:
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
            except Exception as e:
                raise ValueError(f"Error processing schema for route {route}: {str(e)}")
        if self.incoming_output_port and self.incoming_output_port.payload_type is MessagePayload:
            flow_map['input']['message_input'] = {'ports': [self.incoming_output_port]}
        else:
            flow_map['input']['message_input'] = {'payload_type': MessagePayload}
        return flow_map
    
    def setup_schema_message_output(self):
        def pack(pydantic_model: BaseModel) -> SchemaPayload:
            return SchemaPayload(schema=pydantic_model)

        self.ports.add_output(
            name='schema_message_output',
            pack_payload_callback=pack,
            on_connect_callback=lambda port: port.stage_emit(schema=self.pydantic_model)
            )
        # Emits the schema payload when the pydantic model changes
        self.param.watch(
            'pydantic_model',
            lambda event: self.ports.schema_message_output.stage_emit(schema=event.new)
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
                schemas['route'] = {
                    'name': schema_name_str,
                    'pydantic_model': pydantic_model
                    }
        return schemas
    
    def set_pydantic_schema(self, pydantic_schema=None):
        if pydantic_schema:
            self.pydantic_model = pydantic_schema
        else:
            sub_pydantic_models = []
            for schema in self.schemas.values():
                sub_pydantic_models_kwargs = {
                    'route': (str, schema['name']),
                    schema['name']: (schema['pydantic_model'], ...)
                    }
                sub_pydantic_model = create_model('', sub_pydantic_models_kwargs)
                sub_pydantic_models.append(sub_pydantic_model)
            self.pydantic_model = RootModel[Union[*sub_pydantic_models]]

    def flow_fn_setup(self):

        def flow_fn(**kwargs):
            if (active := kwargs['active_input_port']).name == 'message_input':
                route = active.name
                message_content = active.model.content
                model = self.pydantic_model.model_validate_json(message_content)
                if model.route not in self.routing_map:
                    raise ValueError(f"Route {model.route} not found in routing_map keys: {self.routing_map.keys()}")
                output_model = getattr(model, route)
                if transform := self.routing_map[route].get('transform', None):
                    output_payload = transform(output_model)
                else: # Default to message payload
                    json_str = output_model.model_dump_json()
                    output_payload = MessagePayload(content=json_str)
                kwargs[route].emit(output_payload)
            # Set the pydantic schema based on the provided schema input
            elif active.name.endswith('_schema_input'):
                route = active.name.removesuffix('_schema_input')
                if extract_callback := self.routing_map[route]['schema'].get('extract_callback', None):
                    pydantic_schema = extract_callback(active)
                else: # Assume schema payload
                    pydantic_schema = active.model.schema
                self.routing_map[route]['schema']['pydantic_model'] = pydantic_schema

        return flow_fn
            

        

        