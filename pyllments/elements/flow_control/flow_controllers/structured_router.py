import param

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.base.element_base import Element


class StructuredRouterTransformer(Element):
    routing_map = param.Dict(default={}, doc="""
        """)

    flow_controller = param.ClassSelector(class_=FlowController)

    def __init__(self, **params):
        super().__init__(**params)

        