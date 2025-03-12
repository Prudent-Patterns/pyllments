import param

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.base.element_base import Element


class StructuredRouterTransformer(Element):
    routing_map = param.Dict(default={}, doc="""
        routing_map = {
            'reply': {
                'schema': {'response': str}
            },
            'tools': {
                'schema': [mcp_el.ports.tool_list_output],
                'transform': lambda structured_input: ToolCallPayload(tools=structured_input),
                'payload_type': ToolCallPayload,
                'ports': [mcp_el.ports.tool_call_input]
            }
        }
        """)

    flow_controller = param.ClassSelector(class_=FlowController)

    def __init__(self, **params):
        super().__init__(**params)

        