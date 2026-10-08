from typing import Any, Optional, get_origin, get_args

from pyllments.payloads.chunk import ChunkPayload
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.structured import StructuredPayload
from pyllments.payloads.tool_use import ToolUsePayload
from pyllments.payloads.structured.summary_contract import SUMMARY_ARTIFACT_TYPE, summary_artifact_content


def chunk2message(payload, role='user'):
    """
    Converts a ChunkPayload into a MessagePayload.

    Retrieves the text from the chunk's model and assigns a role.
    Default role is 'user' but can be overridden.
    """
    return MessagePayload(content=payload.model.text, role=role)

def chunk_list2message(payload, role='user'):
    """
    Converts a list of ChunkPayloads into a single MessagePayload.

    Concatenates the text from each chunk (with numbering) into a single message.
    Default role is 'user' but can be overridden.
    """
    content_list = [
        f"Chunk {n}:\n{chunk.model.text}"
        for n, chunk in enumerate(payload)
    ]
    return MessagePayload(content='\n'.join(content_list), role=role)

def message2message(payload, role=None):
    """
    Converts a MessagePayload into the new message format.

    Since the payload is already a MessagePayload, it is simply returned.
    If role is provided, it overrides the original role.
    """
    if role is not None:
        # Create a copy with the new role to avoid mutating the original
        return MessagePayload(content=payload.model.content, role=role, mode=payload.model.mode, timestamp=payload.model.timestamp)
    return payload

def message_list2message(payload, role=None):
    """
    Converts a list of MessagePayloads into a message format.

    Returns the list as-is if no role override is specified.
    If role is provided, creates copies with the new role to avoid mutating originals.
    """
    if role is not None:
        # Create copies with the new role to avoid mutating the originals
        return [
            MessagePayload(content=msg.model.content, role=role, mode=msg.model.mode, timestamp=msg.model.timestamp)
            for msg in payload
        ]
    return payload

def tool_use2message(payload, role=None):
    """
    Converts a ToolUsePayload into the messages a model reads.

    Records with provider ids become ``role: tool`` messages; a payload without
    ids renders as one system message. A role override applies only to that
    fallback, since a tool message's role is fixed by the provider.
    """
    messages = payload.to_messages()
    if role is not None:
        messages = [
            MessagePayload(content=m.model.content, role=role, timestamp=m.model.timestamp)
            if m.model.role == 'system' else m
            for m in messages
        ]
    return messages

def tool_use_list2message(payload, role=None):
    """
    Converts a list of ToolUsePayloads into MessagePayloads, in order.
    """
    messages = []
    for item in payload:
        messages.extend(tool_use2message(item, role))
    return messages

def structured2message(payload, role='system'):
    """
    Converts a StructuredPayload into a MessagePayload for LLM context.

    Summary artifacts use a dedicated prefix; other structured data is stringified.
    """
    data = payload.model.data or {}
    if data.get("type") == SUMMARY_ARTIFACT_TYPE:
        prefix = "Conversation summary:\n"
        return MessagePayload(content=prefix + summary_artifact_content(payload), role=role)
    return MessagePayload(content=str(data), role=role)


def schema2message(payload, role='system'):
    """
    Converts a SchemaPayload into a MessagePayload.
    
    Default role is 'system' but can be overridden.
    """
    json = payload.model.schema.schema_json()
    return MessagePayload(content=json, role=role)

payload_message_mapping = {
    ChunkPayload: chunk2message,
    list[ChunkPayload]: chunk_list2message,
    MessagePayload: message2message,
    list[MessagePayload]: message_list2message,
    ToolUsePayload: tool_use2message,
    list[ToolUsePayload]: tool_use_list2message,
    StructuredPayload: structured2message,
}


def _schema_payload_type():
    # Lazy: SchemaPayload imports pydantic, which the Worker entropy patch
    # cannot load during ContextBuilder import.
    from pyllments.payloads.schema import SchemaPayload
    return SchemaPayload

def to_message_payload(payload, payload_message_mapping=payload_message_mapping, expected_type=None, role: Optional[str] = None):
    """
    Converts payloads to MessagePayload format with intelligent role handling.

    Role Assignment Logic:
    - MessagePayload(s): role=None preserves original roles (no mutation), role='x' creates copies with new role
    - Other payloads: role=None uses conversion defaults (chunks='user', tools/schema='system'), role='x' overrides
    
    This ensures existing message roles are preserved while allowing explicit overrides when needed.

    Parameters:
      payload: The input payload to be converted.
      payload_message_mapping (dict): Mapping between payload types and conversion functions.
      expected_type: Optional type to use for determining the conversion function.
      role (str, optional): Role override. None preserves existing roles or uses conversion defaults.
    """
    # Determine the payload type, preferring the expected_type if provided.
    # Some ports can only advertise the container type (`list`) even though the
    # runtime payload is a homogeneous list of message/tool payloads.
    if isinstance(payload, list) and not payload:
        # An empty projection (a fresh ledger) is a valid payload: no messages.
        return []
    payload_type = (expected_type or type(payload)) if expected_type is not Any else type(payload)
    # Normalize typing.List[...] to built-in list[...] for mapping lookup
    origin = get_origin(payload_type)
    if origin is list:
        args = get_args(payload_type)
        if args:
            # Convert typing.List[T] to built-in list[T]
            payload_type = list[args[0]]
    elif payload_type is list and isinstance(payload, list) and payload:
        item_types = {type(item) for item in payload}
        if len(item_types) == 1:
            payload_type = list[next(iter(item_types))]
    try:
        conversion_function = payload_message_mapping[payload_type]
    except KeyError:
        schema_type = _schema_payload_type()
        if payload_type is schema_type:
            conversion_function = schema2message
        else:
            raise ValueError(f"No message payload mapping found for {payload_type}")
    # Non-message payloads use conversion defaults when role is None (e.g. tools -> system).
    if role is None and payload_type not in (MessagePayload, list[MessagePayload]):
        return conversion_function(payload)
    return conversion_function(payload, role)
    
# TODO: integrate with context builder and allow for a tiered port mapping with the payload_message_mapping 
# as a default fallback.
