import param

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
                    'ports': [mcp_el.ports.tool_list_output],
                    'payload_type': ToolListPayload, # Provide if ports not provided
                    'extract_callback': lambda payload: payload.model.schema
                    'name': 'tools' # Default name is the key in the routing_map
                },
                'transform': lambda structured_input: ToolCallPayload(tools=structured_input),
                'ports': [mcp_el.ports.tool_call_input]
                'content_callback': lambda payload: payload.model.content
            }
        }
        """)

    flow_controller = param.ClassSelector(class_=FlowController)

    incoming_output_port = param.ClassSelector(class_=OutputPort)

    def __init__(self, **params):
        super().__init__(**params)

        self.routing_setup()

    def routing_setup(self):
        flow_controller_kwargs = {}
        flow_controller_kwargs['flow_map'] = self.flow_map_setup()
        flow_controller_kwargs['flow_fn'] = self.flow_fn_setup()
        self.flow_controller = FlowController(**flow_controller_kwargs)

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
                    flow_map['input'][input_key] = {'ports': schema_params['ports']}
                elif 'payload_type' in schema_params:
                    flow_map['input'][input_key] = {'payload_type': schema_params['payload_type']}
                elif 'pydantic_model' in schema_params:
                    pass
                else:
                    raise ValueError(f"No valid schema parameters provided for route {route}")
            except Exception as e:
                raise ValueError(f"Error processing schema for route {route}: {str(e)}")
        if self.incoming_output_port:
            flow_map['input']['message_payload_input'] = {'ports': [self.incoming_output_port]}
        else:
            flow_map['input']['message_payload_input'] = {'payload_type': MessagePayload}
        return flow_map

    def flow_fn_setup(self):
        build_fn_kwargs = {}

        def build_fn(**build_fn_kwargs):
            pass
        

        