from typing import Any, Optional

from pyllments.payloads import ChunkPayload, MessagePayload, SchemaPayload, ToolsResponsePayload


def chunk2message(payload):
    """
    Converts a ChunkPayload into a MessagePayload.

    Retrieves the text from the chunk's model and assigns a role of 'human'.
    This ensures that the message is formatted according to our framework's standards.
    """
    return MessagePayload(content=payload.model.text, role='user')

def chunk_list2message(payload):
    """
    Converts a list of ChunkPayloads into a single MessagePayload.

    Concatenates the text from each chunk (with numbering) into a single message.
    The resulting message is designated with a 'human' role.
    """
    content_list = [
        f"Chunk {n}:\n{chunk.model.text}"
        for n, chunk in enumerate(payload)
    ]
    return MessagePayload(content='\n'.join(content_list), role='user')

def message2message(payload):
    """
    Converts a MessagePayload into the new message format.

    Since the payload is already a MessagePayload, it is simply returned.
    """
    return payload

def message_list2message(payload):
    """
    Converts a list of MessagePayloads into a message format.

    Currently, this function returns the list as-is. Future revisions might combine
    the individual payloads into one aggregated MessagePayload if needed.
    """
    return payload

def tools_response2message(payload):
    
    return MessagePayload(content=payload.model.content, role='system')

def tools_response_list2message(payload):
    pass

def schema2message(payload):
    json = payload.model.schema.schema_json()
    return MessagePayload(content=json, role='system')

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
    Converts an input payload to a MessagePayload using a mapping of conversion functions.

    This function determines the payload's type (or uses an expected type if provided)
    and then applies the corresponding conversion function. If no mapping is found,
    a ValueError is raised.

    Additionally, if a role is provided, it will override the role in the resulting MessagePayload(s).

    Parameters:
      payload: The input payload to be converted.
      payload_message_mapping (dict): Mapping between payload types and conversion functions.
      expected_type: Optional type to use for determining the conversion function. If not provided, the payload's type is used.
      role (str, optional): If provided, override the role in the resulting MessagePayload(s) regardless of the default.
    """
    payload_type = (expected_type or type(payload)) if expected_type is not Any else type(payload)
    try:
        conversion_function = payload_message_mapping[payload_type]
        return_val = conversion_function(payload)
        if role is not None:
            if isinstance(return_val, list):
                for msg in return_val:
                    msg.model.role = role
            else:
                return_val.model.role = role
        return return_val
    except KeyError:
        raise ValueError(f"No message payload mapping found for {payload_type}")
    
# TODO: integrate with context builder and allow for a tiered port mapping with the payload_message_mapping 
# as a default fallback.
