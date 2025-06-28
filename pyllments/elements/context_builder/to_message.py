from typing import Any, Optional, get_origin, get_args

from pyllments.payloads import ChunkPayload, MessagePayload, SchemaPayload, ToolsResponsePayload


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

def tools_response2message(payload, role='system'):
    """
    Converts a ToolsResponsePayload into a MessagePayload.
    
    Default role is 'system' but can be overridden.
    """
    return MessagePayload(content=payload.model.content, role=role)

def tools_response_list2message(payload, role='system'):
    """
    Converts a list of ToolsResponsePayloads into MessagePayloads.
    
    Default role is 'system' but can be overridden.
    """
    return [
        MessagePayload(content=item.model.content, role=role)
        for item in payload
    ]

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
    ToolsResponsePayload: tools_response2message,
    list[ToolsResponsePayload]: tools_response_list2message,
    SchemaPayload: schema2message,

}

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
    # Determine the payload type, preferring the expected_type if provided
    payload_type = (expected_type or type(payload)) if expected_type is not Any else type(payload)
    # Normalize typing.List[...] to built-in list[...] for mapping lookup
    origin = get_origin(payload_type)
    if origin is list:
        args = get_args(payload_type)
        if args:
            # Convert typing.List[T] to built-in list[T]
            payload_type = list[args[0]]
    try:
        # Lookup conversion function for the normalized payload type
        conversion_function = payload_message_mapping[payload_type]
        return conversion_function(payload, role)
    except KeyError:
        raise ValueError(f"No message payload mapping found for {payload_type}")
    
# TODO: integrate with context builder and allow for a tiered port mapping with the payload_message_mapping 
# as a default fallback.
