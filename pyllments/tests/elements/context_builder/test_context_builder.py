from pyllments.elements import ContextBuilder, PipeElement
from pyllments.payloads import MessagePayload

def print_message_list(messages, prefix=""):
    """Helper function to print a list of messages in a readable format"""
    print(f"\n{prefix}")
    for i, msg in enumerate(messages):
        print(f"{i+1}. [{msg.model.role}]: {msg.model.content}")

def test_context_builder_trigger_map():
    print("\n=== Testing ContextBuilder Trigger Map Functionality ===")
    
    # Create pipe elements for input and output
    input_pipe_a = PipeElement()
    input_pipe_b = PipeElement()
    output_pipe = PipeElement()

    # Create a context builder with both connected_input_map and trigger_map
    context_builder = ContextBuilder(
        connected_input_map={
            'port_a': ('user', [input_pipe_a.ports.output['pipe_output']]),
            'port_b': ('assistant', [input_pipe_b.ports.output['pipe_output']]),
            'system_msg': ('system', "You are a helpful assistant.")
        },
        trigger_map={
            'port_a': ['port_a', 'port_b', 'system_msg'],  # When port_a triggers, wait for port_b
            'port_b': ['port_b', 'system_msg']  # When port_b triggers, build immediately
        },
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    # Setup a callback to print received messages
    def print_received(payload):
        if isinstance(payload, list):
            print_message_list(payload, "Received messages:")
        else:
            print(f"Received single message: [{payload.model.role}]: {payload.model.content}")
        return payload

    output_pipe.receive_callback = print_received

    print("\n=== Test Scenario 1: Send to port_b first ===")
    print("This should build immediately with assistant message + system message")
    assistant_message = MessagePayload(content="This is an assistant response", role="assistant")
    print(f"\nSending assistant message to port_b: {assistant_message.model.content}")
    input_pipe_b.send_payload(assistant_message)

    print("\n=== Test Scenario 2: Send to port_a first, then port_b ===")
    print("This should wait for port_b before building")
    user_message = MessagePayload(content="Hello, how are you?", role="user")
    print(f"\nSending user message to port_a: {user_message.model.content}")
    input_pipe_a.send_payload(user_message)
    
    print("\nNothing should be emitted yet since we're waiting for port_b...")
    
    assistant_message_2 = MessagePayload(content="I'm doing well!", role="assistant")
    print(f"\nNow sending assistant message to port_b: {assistant_message_2.model.content}")
    input_pipe_b.send_payload(assistant_message_2)

def test_context_builder_build_fn():
    print("\n=== Testing ContextBuilder Build Function Functionality ===")
    
    input_pipe_a = PipeElement()
    input_pipe_b = PipeElement()
    output_pipe = PipeElement()

    def custom_build_fn(port_a, port_b, messages_output, active_input_port, c):
        """Custom build function that reverses the order based on which port triggered
        
        Args:
            port_a: flow port for user messages
            port_b: flow port for assistant messages
            messages_output: output port for emitting messages
            active_input_port: the port that triggered this build
            c: context dictionary containing preset_messages
        
        Returns:
            list of flow ports and/or preset message keys in desired order
        """
        if active_input_port.name == 'port_a':
            # When user message triggers, use reverse order
            return ['system_msg', port_b, port_a]  # Reverse order when port_a triggers
        else:
            # When assistant message triggers, use normal order
            return [port_b, 'system_msg']  # Normal order when port_b triggers

    context_builder = ContextBuilder(
        connected_input_map={
            'port_a': ('user', [input_pipe_a.ports.output['pipe_output']]),
            'port_b': ('assistant', [input_pipe_b.ports.output['pipe_output']]),
            'system_msg': ('system', "You are a helpful assistant.")
        },
        build_fn=custom_build_fn,
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    def print_received(payload):
        if isinstance(payload, list):
            print_message_list(payload, "Received messages:")
        else:
            print(f"Received single message: [{payload.model.role}]: {payload.model.content}")
        return payload

    output_pipe.receive_callback = print_received

    print("\n=== Test Scenario 1: Send to port_b first ===")
    print("This should build immediately with assistant message + system message")
    assistant_message = MessagePayload(content="This is an assistant response", role="assistant")
    print(f"\nSending assistant message to port_b: {assistant_message.model.content}")
    input_pipe_b.send_payload(assistant_message)

    print("\n=== Test Scenario 2: Send to port_a first ===")
    print("This should build with messages in reverse order")
    user_message = MessagePayload(content="Hello, how are you?", role="user")
    print(f"\nSending user message to port_a: {user_message.model.content}")
    input_pipe_a.send_payload(user_message)

def test_context_builder_default():
    print("\n=== Testing ContextBuilder Default Flow Function ===")
    
    input_pipe_a = PipeElement()
    input_pipe_b = PipeElement()
    output_pipe = PipeElement()

    context_builder = ContextBuilder(
        connected_input_map={
            'port_a': ('user', [input_pipe_a.ports.output['pipe_output']]),
            'port_b': ('assistant', [input_pipe_b.ports.output['pipe_output']]),
            'system_msg': ('system', "You are a helpful assistant.")
        },
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    def print_received(payload):
        if isinstance(payload, list):
            print_message_list(payload, "Received messages:")
        else:
            print(f"Received single message: [{payload.model.role}]: {payload.model.content}")
        return payload

    output_pipe.receive_callback = print_received

    print("\n=== Test Scenario: Send messages in any order ===")
    print("Default behavior waits for all non-string messages before building")
    
    print("\nSending user message first...")
    user_message = MessagePayload(content="Hello!", role="user")
    input_pipe_a.send_payload(user_message)
    
    print("\nSending assistant message second...")
    assistant_message = MessagePayload(content="Hi there!", role="assistant")
    input_pipe_b.send_payload(assistant_message)

if __name__ == "__main__":
    print("\nRunning trigger_map test...")
    test_context_builder_trigger_map()
    
    print("\nRunning build_fn test...")
    test_context_builder_build_fn()
    
    print("\nRunning default flow test...")
    test_context_builder_default()
