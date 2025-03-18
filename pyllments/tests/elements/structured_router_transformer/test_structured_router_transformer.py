import pytest

from pydantic import RootModel

from pyllments.logging import setup_logging
from pyllments.elements import StructuredRouterTransformer, PipeElement
from pyllments.payloads import MessagePayload


setup_logging()

@pytest.fixture
def structured_router_transformer_pipe_el():
    structured_router_transformer = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': MessagePayload,
            },
            'other_reply': {
                'schema': {'pydantic_model': str},
                'payload_type': MessagePayload,
            }
        }
    )
    pipe_el = PipeElement(receive_callback=lambda x: x.model.schema.model_json_schema())
    return structured_router_transformer, pipe_el

def test_structured_router_transformer(structured_router_transformer_pipe_el):
    structured_router_transformer, pipe_el = structured_router_transformer_pipe_el
    structured_router_transformer.ports.schema_output > pipe_el.ports.pipe_input
    