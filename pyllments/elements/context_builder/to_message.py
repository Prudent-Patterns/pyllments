from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload


def chunk2message(payload):
    return MessagePayload(message=HumanMessage(content='blah blah blah'), mode='atomic')

def chunk_list2message(payload):
    """Converts a list of ChunkPayloads into a message format."""
    return MessagePayload(message=HumanMessage(content='chunk list message'), mode='atomic')

def message2message(payload):
    """Converts a MessagePayload into a message format."""
    return MessagePayload(message=HumanMessage(content='message payload message'), mode='atomic')

def message_list2message(payload):
    """Converts a list of MessagePayloads into a message format."""
    return MessagePayload(message=HumanMessage(content='message list message'), mode='atomic')

def human_message2message(payload):
    """Converts a HumanMessage into a message format."""
    return MessagePayload(message=HumanMessage(content='human message'), mode='atomic')

def ai_message2message(payload):
    """Converts an AIMessage into a message format."""
    return MessagePayload(message=HumanMessage(content='AI message'), mode='atomic')

def system_message2message(payload):
    """Converts a SystemMessage into a message format."""
    return MessagePayload(message=HumanMessage(content='system message'), mode='atomic')


payload_message_mapping = {
    ChunkPayload: chunk2message,
    list[ChunkPayload]: chunk_list2message,
    MessagePayload: message2message,
    list[MessagePayload]: message_list2message,
    HumanMessage: human_message2message,
    AIMessage: ai_message2message,
    SystemMessage: system_message2message,
}

def to_message_payload(payload, payload_message_mapping=payload_message_mapping):
    payload_type = type(payload)
    try:
        return payload_message_mapping[payload_type](payload)
    except KeyError:
        raise ValueError(f"No message payload mapping found for {payload_type}")