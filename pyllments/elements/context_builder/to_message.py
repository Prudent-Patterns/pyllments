from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload


def chunk2message(payload):
    """Converts a ChunkPayload into a MessagePayload."""
    return MessagePayload(message=HumanMessage(content='blah blah blah'), mode='atomic')

def chunk_list2message(payload):
    """Converts a list of ChunkPayloads into a message format."""
    content_list = [
        f"Chunk {n}:\n{chunk.model.text}"
        for n, chunk
        in enumerate(payload)
    ]
    return MessagePayload(message=HumanMessage(content='\n'.join(content_list)), mode='atomic')

def message2message(payload):
    """Converts a MessagePayload into a message format."""
    return payload

def message_list2message(payload):
    """Converts a list of MessagePayloads into a message format."""
    return payload

payload_message_mapping = {
    ChunkPayload: chunk2message,
    list[ChunkPayload]: chunk_list2message,
    MessagePayload: message2message,
    list[MessagePayload]: message_list2message,
}

def to_message_payload(payload, payload_message_mapping=payload_message_mapping, expected_type=None):
    payload_type = expected_type or type(payload)
    try:
        conversion_function = payload_message_mapping[payload_type]
        return conversion_function(payload)
    except KeyError:
        raise ValueError(f"No message payload mapping found for {payload_type}")
    
# TODO: integrate with context builder and allow for a tiered port mapping with the payload_message_mapping as a default fallback
