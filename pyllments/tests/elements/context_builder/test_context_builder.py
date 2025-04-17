import pytest
import re
import asyncio
from pyllments.elements import ContextBuilderElement, PipeElement
from pyllments.payloads import MessagePayload
from pyllments.common.loop_registry import LoopRegistry

# Helper to flush the event loop so async work completes

def run_loop_briefly(duration=0.1):
    loop = LoopRegistry.get_loop()
    stop_time = loop.time() + duration
    while loop.time() < stop_time:
        loop.run_until_complete(asyncio.sleep(0.01))

# Helper assertion for message content

def assert_message_content(received_messages, index, role, content_substring=None, exact_content=None):
    assert index < len(received_messages), \
        f"Expected message at index {index}, but only received {len(received_messages)} messages"
    msg = received_messages[index]
    assert msg.model.role == role, f"Message {index} role mismatch"
    if exact_content is not None:
        assert msg.model.content == exact_content, f"Message {index} content mismatch"
    if content_substring is not None:
        assert content_substring in msg.model.content, \
            f"Message {index} does not contain expected substring: {content_substring}"

@pytest.fixture

def output_pipe_and_messages():
    pipe = PipeElement(name="output")
    received = []
    def capture_messages(payload):
        received.clear()
        if isinstance(payload, list):
            received.extend(payload)
        else:
            received.append(payload)
        return payload
    pipe.ports.input['pipe_input'].unpack_payload_callback = capture_messages
    return pipe, received


def test_basic_routing(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {
                'role': 'user',
                'ports': [user_input.ports.output['pipe_output']],
                'persist': True
            },
            'assistant_msg': {
                'role': 'assistant',
                'ports': [assistant_input.ports.output['pipe_output']]
            }
        },
        emit_order=['user_msg', 'assistant_msg'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    # Send only the user message, expect no emission
    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    run_loop_briefly()
    assert len(received) == 0, "No messages should be emitted with just one input"

    # Send assistant message to trigger emit_order
    assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "user", exact_content="Hello")
    assert_message_content(received, 1, "assistant", exact_content="Hi there")


def test_constants_and_templates(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']]},
            'system_constant': {'role': 'system', 'message': "You are a helpful assistant."},
            'user_template': {'role': 'system', 'template': "The user said: {{ user_msg }}"}
        },
        emit_order=['system_constant', 'user_template', 'user_msg'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    user_input.send_payload(MessagePayload(content="How does this work?", role="user"))
    run_loop_briefly()
    assert len(received) == 3
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "system", content_substring="The user said: How does this work?")
    assert_message_content(received, 2, "user", exact_content="How does this work?")


def test_emit_order(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {
                'role': 'user',
                'ports': [user_input.ports.output['pipe_output']],
                'persist': True
            },
            'assistant_msg': {
                'role': 'assistant',
                'ports': [assistant_input.ports.output['pipe_output']],
                'persist': True
            },
            'system_constant': {'role': 'system', 'message': "You are a helpful assistant."}
        },
        emit_order=['system_constant', 'user_msg', 'assistant_msg'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    user_input.send_payload(MessagePayload(content="What is AI?", role="user"))
    run_loop_briefly()
    assert len(received) == 0

    assistant_input.send_payload(MessagePayload(content="AI is artificial intelligence.", role="assistant"))
    run_loop_briefly()
    assert len(received) == 3
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="What is AI?")
    assert_message_content(received, 2, "assistant", exact_content="AI is artificial intelligence.")


def test_trigger_map(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']]},
            'system_constant': {'role': 'system', 'message': "You are a helpful assistant."}
        },
        trigger_map={
            'user_msg': ['system_constant', 'user_msg'],
            'assistant_msg': ['system_constant', 'user_msg', 'assistant_msg']
        },
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    # User trigger
    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello")

    received.clear()
    # Assistant trigger
    assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
    run_loop_briefly()
    assert len(received) == 3
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello")
    assert_message_content(received, 2, "assistant", exact_content="Hi there")


def test_build_fn(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")

    def custom_build_fn(active_input_port, **kwargs):
        if active_input_port.name == 'user_msg':
            return ['system_constant', 'user_msg']
        elif active_input_port.name == 'assistant_msg':
            return ['assistant_msg', 'user_msg', 'system_constant']
        return None

    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']]},
            'system_constant': {'role': 'system', 'message': "You are a helpful assistant."}
        },
        build_fn=custom_build_fn,
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )

    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello")

    received.clear()
    assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
    run_loop_briefly()
    assert len(received) == 3
    assert_message_content(received, 0, "assistant", exact_content="Hi there")
    assert_message_content(received, 1, "user", exact_content="Hello")
    assert_message_content(received, 2, "system", exact_content="You are a helpful assistant.")

def test_port_persistence(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']]}
        },
        emit_order=['user_msg', 'assistant_msg'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Send initial messages
    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    assistant_input.send_payload(MessagePayload(content="Hi", role="assistant"))
    run_loop_briefly()
    # Clear for next round
    received.clear()
    # Send new assistant message to test persistence
    assistant_input.send_payload(MessagePayload(content="How are you?", role="assistant"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "user", exact_content="Hello")
    assert_message_content(received, 1, "assistant", exact_content="How are you?")


def test_template_with_persisted_ports(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']]},
            'summary_template': {'role': 'system', 'template': "Last user message: {{ user_msg }}"}
        },
        emit_order=['user_msg', 'assistant_msg', 'summary_template'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Send initial messages
    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    assistant_input.send_payload(MessagePayload(content="Hi", role="assistant"))
    run_loop_briefly()
    received.clear()
    # Send new assistant message to trigger template
    assistant_input.send_payload(MessagePayload(content="How are you?", role="assistant"))
    run_loop_briefly()
    assert len(received) == 3
    assert_message_content(received, 0, "user", exact_content="Hello")
    assert_message_content(received, 1, "assistant", exact_content="How are you?")
    assert_message_content(received, 2, "system", content_substring="Last user message: Hello")


def test_template_processing(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']], 'persist': True},
            'simple_template': {'role': 'system', 'template': "User query: {{ user_msg }}"},
            'conversation_template': {'role': 'system', 'template': "Conversation:\nUser: {{ user_msg }}\nAssistant: {{ assistant_msg }}"}
        },
        trigger_map={
            'user_msg': ['user_msg', 'simple_template'],
            'assistant_msg': ['user_msg', 'assistant_msg', 'conversation_template']
        },
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Test user message trigger
    user_input.send_payload(MessagePayload(content="What is Python?", role="user"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "user", exact_content="What is Python?")
    assert_message_content(received, 1, "system", content_substring="User query: What is Python?")
    received.clear()
    # Test assistant message trigger
    assistant_input.send_payload(MessagePayload(content="Python is a programming language.", role="assistant"))
    run_loop_briefly()
    assert len(received) == 3
    assert_message_content(received, 0, "user", exact_content="What is Python?")
    assert_message_content(received, 1, "assistant", exact_content="Python is a programming language.")
    assert_message_content(received, 2, "system", content_substring="User: What is Python?")
    assert_message_content(received, 2, "system", content_substring="Assistant: Python is a programming language.")


def test_template_waits_for_all(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    extra_input = PipeElement(name="extra_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'extra_msg': {'role': 'assistant', 'ports': [extra_input.ports.output['pipe_output']], 'persist': True},
            'dependent_template': {'role': 'system', 'template': "Combined: {{ user_msg }} and {{ extra_msg }}"}
        },
        emit_order=['user_msg', 'dependent_template'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Send only the user message
    user_input.send_payload(MessagePayload(content="Hello from user", role="user"))
    run_loop_briefly()
    assert len(received) == 0
    # Now send the extra message to satisfy template
    extra_input.send_payload(MessagePayload(content="Hello from extra", role="assistant"))
    run_loop_briefly()
    assert len(received) == 2
    # Verify combined content
    assert "Hello from user" in received[1].model.content
    assert "Hello from extra" in received[1].model.content

def test_callback(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    # Define a callback that appends text
    def transform_callback(payload):
        return MessagePayload(content=payload.model.content + " - callback", role=payload.model.role)
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {
                'role': 'user',
                'ports': [user_input.ports.output['pipe_output']],
                'callback': transform_callback
            }
        },
        emit_order=['user_msg'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    test_payload = MessagePayload(content="Test message", role="user")
    user_input.send_payload(test_payload)
    run_loop_briefly()
    assert len(received) == 1
    transformed = received[0]
    assert transformed.model.content == "Test message - callback"
    assert transformed.model.role == "user"


def test_flow_controller_persistence(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']]},
            'msg_constant': {'role': 'system', 'message': "This is a constant"},
            'msg_template': {'role': 'system', 'template': "User said: {{ user_msg }}"}
        },
        emit_order=['msg_constant', 'user_msg', 'msg_template', 'assistant_msg'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Verify flow_map and storages
    fmap = context_builder.flow_controller.flow_map['input']
    assert 'user_msg' in fmap
    assert 'assistant_msg' in fmap
    assert 'msg_constant' not in fmap
    assert 'msg_template' not in fmap
    assert 'msg_constant' in context_builder.constants
    assert 'msg_template' in context_builder.templates
    # Send messages
    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    assistant_input.send_payload(MessagePayload(content="Hi", role="assistant"))
    run_loop_briefly()
    received.clear()
    # Send new assistant message
    assistant_input.send_payload(MessagePayload(content="How are you?", role="assistant"))
    run_loop_briefly()
    # Expect constant, persisted user, template, then assistant
    assert len(received) == 4
    assert_message_content(received, 0, "system", exact_content="This is a constant")
    assert_message_content(received, 1, "user", exact_content="Hello")
    assert_message_content(received, 2, "system", content_substring="User said: Hello")
    assert_message_content(received, 3, "assistant", exact_content="How are you?")


def test_template_storage(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']], 'persist': True},
            'convo_template': {'role': 'system', 'template': "Conversation:\nUser: {{ user_msg }}\nAssistant: {{ assistant_msg }}"}
        },
        emit_order=['user_msg', 'assistant_msg', 'convo_template'],
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Load user message
    user_input.send_payload(MessagePayload(content="What is Python?", role="user"))
    run_loop_briefly()
    # Template storage should have the user payload
    assert 'convo_template' in context_builder.template_storage
    assert 'user_msg' in context_builder.template_storage['convo_template']
    # Load assistant message
    assistant_input.send_payload(MessagePayload(content="Python is a programming language.", role="assistant"))
    run_loop_briefly()
    # Now storage includes both
    assert 'assistant_msg' in context_builder.template_storage['convo_template']
    # Verify emitted content
    assert len(received) == 3
    content = received[2].model.content
    assert "User: What is Python?" in content
    assert "Assistant: Python is a programming language." in content


def test_optional_items(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    assistant_input = PipeElement(name="assistant_input")
    optional_input = PipeElement(name="optional_input")
    context_builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'assistant_msg': {'role': 'assistant', 'ports': [assistant_input.ports.output['pipe_output']], 'persist': True},
            'optional_msg': {'role': 'user', 'ports': [optional_input.ports.output['pipe_output']], 'persist': True},
            'system_constant': {'role': 'system', 'message': "You are a helpful assistant."},
            'optional_dep_template': {'role': 'system', 'template': "Required: {{ user_msg }} - Optional: {{ optional_msg }}"},
            'required_template': {'role': 'system', 'template': "User: {{ user_msg }} Assistant: {{ assistant_msg }}"}
        },
        trigger_map={
            'user_msg': ['system_constant', 'user_msg', '[optional_msg]', '[optional_dep_template]'],
            'assistant_msg': ['system_constant', 'user_msg', 'assistant_msg', '[optional_msg]', 'required_template']
        },
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Case 1: optional missing
    user_input.send_payload(MessagePayload(content="Hello", role="user"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello")
    received.clear()
    # Case 2: add optional and retrigger
    optional_input.send_payload(MessagePayload(content="Optional content", role="user"))
    run_loop_briefly()
    user_input.send_payload(MessagePayload(content="Hello again", role="user"))
    run_loop_briefly()
    assert len(received) == 4
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello again")
    assert_message_content(received, 2, "user", exact_content="Optional content")
    assert_message_content(received, 3, "system", content_substring="Required: Hello again - Optional: Optional content")
    received.clear()
    # Case 3: assistant trigger with optional
    assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
    run_loop_briefly()
    assert len(received) == 5
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello again")
    assert_message_content(received, 2, "assistant", exact_content="Hi there")
    assert_message_content(received, 3, "user", exact_content="Optional content")
    assert_message_content(received, 4, "system", content_substring="User: Hello again Assistant: Hi there")
    received.clear()

# Split dependency+optionality scenarios into separate pytest functions

def test_case1_required_items_with_and_without_history(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    history_input = PipeElement(name="history_input")
    case_input = PipeElement(name="case1_input")
    sample_history = [MessagePayload(content="Previous message 1", role="user"),
                      MessagePayload(content="Previous response 1", role="user")]
    sample_user = MessagePayload(content="Hello", role="user")
    builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'history': {'payload_type': list[MessagePayload], 'ports': [history_input.ports.output['pipe_output']], 'persist': True},
            'case1_trigger': {'role': 'user', 'ports': [case_input.ports.output['pipe_output']]},
            'main_system_message_constant': {'role': 'system', 'message': "You are a helpful assistant."},
            'history_template': {'role': 'system', 'template': "History available: {{ history }}", 'depends_on': 'history'}
        },
        trigger_map={'case1_trigger': ['main_system_message_constant', 'history_template', 'history', 'user_msg']},
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Without history
    user_input.send_payload(sample_user)
    run_loop_briefly()
    received.clear()
    case_input.send_payload(MessagePayload(content="Trigger case 1", role="user"))
    run_loop_briefly()
    assert len(received) == 0
    # With history
    user_input.send_payload(sample_user)
    history_input.send_payload(sample_history)
    run_loop_briefly()
    received.clear()
    case_input.send_payload(MessagePayload(content="Trigger case 1", role="user"))
    run_loop_briefly()
    assert len(received) == 5
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "system", content_substring="History available:")
    assert_message_content(received, 2, "user", exact_content="Previous message 1")
    assert_message_content(received, 3, "user", exact_content="Previous response 1")
    assert_message_content(received, 4, "user", exact_content="Hello")

def test_case2_optional_items_skipped_and_included(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    history_input = PipeElement(name="history_input")
    case_input = PipeElement(name="case2_input")
    sample_history = [MessagePayload(content="Previous message 1", role="user"),
                      MessagePayload(content="Previous response 1", role="user")]
    sample_user = MessagePayload(content="Hello", role="user")
    builder = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'history': {'payload_type': list[MessagePayload], 'ports': [history_input.ports.output['pipe_output']], 'persist': True},
            'case2_trigger': {'role': 'user', 'ports': [case_input.ports.output['pipe_output']]},
            'main_system_message_constant': {'role': 'system', 'message': "You are a helpful assistant."},
            'history_template': {'role': 'system', 'template': "History available: {{ history }}", 'depends_on': 'history'}
        },
        trigger_map={'case2_trigger': ['main_system_message_constant', '[history_template]', '[history]', 'user_msg']},
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    # Without history
    user_input.send_payload(sample_user)
    run_loop_briefly()
    case_input.send_payload(MessagePayload(content="Trigger case 2", role="user"))
    run_loop_briefly()
    assert len(received) == 2
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "user", exact_content="Hello")
    # With history
    history_input.send_payload(sample_history)
    run_loop_briefly()
    received.clear()
    case_input.send_payload(MessagePayload(content="Trigger case 2", role="user"))
    run_loop_briefly()
    assert len(received) == 5
    assert_message_content(received, 0, "system", exact_content="You are a helpful assistant.")
    assert_message_content(received, 1, "system", content_substring="History available:")
    assert_message_content(received, 2, "user", exact_content="Previous message 1")
    assert_message_content(received, 3, "user", exact_content="Previous response 1")
    assert_message_content(received, 4, "user", exact_content="Hello")

def test_case3_required_template_with_dependency(output_pipe_and_messages):
    output_pipe, received = output_pipe_and_messages
    user_input = PipeElement(name="user_input")
    case3_input = PipeElement(name="case3_input")
    sample_user_msg = MessagePayload(content="Hello", role="user")
    builder3_no = ContextBuilderElement(
        input_map={
            'user_msg': {'role': 'user', 'ports': [user_input.ports.output['pipe_output']], 'persist': True},
            'case3_trigger': {'role': 'user', 'ports': [case3_input.ports.output['pipe_output']]},
            'main_system_message_constant': {'role': 'system', 'message': "You are a helpful assistant."},
            'history_template': {'role': 'system', 'template': "History available: {{ history }}", 'depends_on': 'history'}
        },
        trigger_map={'case3_trigger': ['main_system_message_constant', 'history_template', 'history', 'user_msg']},
        outgoing_input_port=output_pipe.ports.input['pipe_input']
    )
    user_input.send_payload(sample_user_msg)
    run_loop_briefly()
    # Clear any messages left over from previous cases
    received.clear()
    case3_input.send_payload(MessagePayload(content="Trigger case 3", role="user"))
    run_loop_briefly()
    assert len(received) == 0
