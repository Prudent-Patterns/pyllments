import json
from os import name
from typing import Union, Literal
import asyncio

import param
from pydantic import BaseModel, create_model, RootModel, Field
from loguru import logger
from pydantic.config import ConfigDict

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
        A dictionary defining the routing logic. Each key is a route name.
        The value is a dict with a single key 'outputs', whose value is an ordered mapping
        from data_field names to spec dicts, each with:
        
        - 'schema': dict defining the Pydantic model for that field.
            - 'pydantic_model': type[BaseModel] or basic type.
            - OR 'ports': list of InputPorts for schema updates.
        - 'ports': list[InputPort] that the output port should connect to.
        - 'payload_type': (optional) the Payload class to emit; defaults to StructuredPayload.
        - 'transform': (optional) function(value) -> Payload instance.
        
        Example:
        routing_map = {
            'reply': {
                'outputs': {
                    'message': {
                        'schema': {'pydantic_model': str},
                        'ports': [chat_interface_el.ports.message_input],
                        'transform': lambda txt: MessagePayload(content=txt, role='assistant')
                    },
                    'reasoning': {
                        'schema': {'pydantic_model': str},
                        'ports': [some_other_port],
                        'transform': lambda r: MessagePayload(content=f'Reason: {r}')
                    }
                }
            },
            'tools': {
                'outputs': {
                    'tools': {
                        'schema': {'ports': [some_schema_port]},
                        'payload_type': StructuredPayload
                    },
                    'reasoning': {
                        'schema': {'pydantic_model': str},
                        'ports': [some_other_port],
                        'transform': lambda r: MessagePayload(content=f'Reason: {r}')
                    }
                }
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
        # Each route must define an 'outputs' mapping of data_field -> spec
        for route, route_params in self.routing_map.items():
            outputs = route_params.get('outputs')
            if outputs is None:
                raise ValueError(f"No 'outputs' defined for route {route}")
            for data_field, spec in outputs.items():
                alias = f"{route}_{data_field}"
                # configure the output port for this field
                if ports := spec.get('ports'):
                    flow_map['output'][alias] = {'ports': ports}
                elif payload_type := spec.get('payload_type'):
                    flow_map['output'][alias] = {'payload_type': payload_type}
                else:
                    raise ValueError(f"No ports or payload_type provided for output '{data_field}' in route '{route}'")
                # configure schema input port for this field
                # only ports list is supported; payload_type always defaults to SchemaPayload
                schema_spec = spec.get('schema', {})
                input_key = f"{alias}_schema_input"
                if 'ports' in schema_spec:
                    flow_map['input'][input_key] = {
                        'ports': schema_spec['ports'],
                        'persist': True,
                    }
                elif 'pydantic_model' in schema_spec:
                    # pydantic model provided directly—no schema input port needed
                    pass
                elif 'payload_type' in schema_spec:
                    # payload_type provided—create schema input port expecting that payload
                    flow_map['input'][input_key] = {
                        'payload_type': schema_spec['payload_type'],
                        'persist': True,
                    }
                else:
                    raise ValueError(f"No valid schema parameters for output '{data_field}' in route '{route}'")
        # incoming message_input mapping (unchanged)
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
        
    def _build_route_model(self, route, params):
        """
        Helper to build a Pydantic sub-model for a single route, including titles and descriptions.
        """
        outputs = params.get('outputs', {})
        if not outputs:
            return None
        # Route-level description metadata
        route_desc = params.get('description')
        # Build field definitions with optional descriptions
        # Always include 'route' discriminator field without description, validation via Literal
        fields = {'route': (Literal[route], ...)}
        added = False
        for field_name, spec in outputs.items():
            schema_spec = spec.get('schema', {})
            if 'pydantic_model' in schema_spec:
                p_mod = schema_spec['pydantic_model']
                field_desc = spec.get('description')
                if field_desc:
                    fields[field_name] = (p_mod, Field(..., description=field_desc))
                else:
                    fields[field_name] = (p_mod, ...)
                added = True
        if not added:
            return None
        # Assemble ConfigDict merging CleanModel JSON schema hook and title, with optional description
        config_kwargs = {**CleanModel.model_config, 'title': f"{route}_route"}
        if route_desc is not None:
            config_kwargs['description'] = route_desc
        config = ConfigDict(**config_kwargs)
        return create_model(f"{route}_route", __config__=config, **fields)

    def set_pydantic_schema(self, pydantic_schema=None):
        """
        Builds a unified RootModel union from each route's sub-models.
        """
        if pydantic_schema:
            self.pydantic_model = pydantic_schema
            return

        sub_models = []
        for route, params in self.routing_map.items():
            model = self._build_route_model(route, params)
            if model:
                sub_models.append(model)

        if not sub_models:
            raise ValueError("No valid route sub-models generated for schema")

        # Combine all route models into a discriminated union RootModel
        self.pydantic_model = create_model(
            '',
            __base__=(RootModel[Union[*sub_models]], CleanModel),
        )

    def flow_fn_setup(self):

        async def flow_fn(**kwargs):
            active = kwargs['active_input_port']
            # Handle incoming JSON messages
            if active.name == 'message_input':
                message_content = await active.payload.model.aget_message()
                self.logger.debug(f"Incoming JSON: {message_content}")
                if not message_content or message_content.strip() == "":
                    self.logger.error("Received empty message content")
                    return
                try:
                    validated = self.pydantic_model.model_validate_json(message_content).root
                    route = validated.route
                    if route not in self.routing_map:
                        raise ValueError(f"Unknown route '{route}'")
                    # Emit each defined output field
                    for field_name, spec in self.routing_map[route]['outputs'].items():
                        value = getattr(validated, field_name)
                        data = value.model_dump() if isinstance(value, BaseModel) else value
                        # Apply transform or default to payload_type
                        if transform := spec.get('transform'):
                            payload = transform(data)
                        else:
                            PayloadClass = spec.get('payload_type', StructuredPayload)
                            payload = PayloadClass(data=data)
                        port_alias = f"{route}_{field_name}"
                        await kwargs[port_alias].emit(payload)
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    self.logger.error(f"Schema expected: {self.pydantic_model.model_json_schema()}")
                    return
            # Handle schema updates for each output field
            elif active.name.endswith('_schema_input'):
                alias = active.name.removesuffix('_schema_input')
                updated = False
                for route, params in self.routing_map.items():
                    for field_name, spec in params.get('outputs', {}).items():
                        if alias == f"{route}_{field_name}":
                            schema_spec = spec['schema']
                            if extract := schema_spec.get('extract_callback'):
                                new_model = extract(active)
                            else:
                                new_model = active.payload.model.schema
                            schema_spec['pydantic_model'] = new_model
                            self.set_pydantic_schema()
                            self.logger.debug(
                                f"Updated schema for {alias}: {self.pydantic_model.model_json_schema()}"
                            )
                            updated = True
                            break
                    if updated:
                        break
        return flow_fn