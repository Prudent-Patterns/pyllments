import param
from pyllments.elements import ContextBuilderElement, PipeElement
from pyllments.payloads import MessagePayload
import unittest
import re

class TestContextBuilder(unittest.TestCase):
    """Test suite for ContextBuilder with simple input/output tests for each feature."""
    
    def setUp(self):
        """Setup common test fixtures."""
        print("\n----- Setting up test fixtures -----")
        # Create an output pipe element for capturing emitted messages
        self.output_pipe = PipeElement(name="output")
        self.received_messages = []
        
        # Setup a callback to capture emitted messages
        def capture_messages(payload):
            if isinstance(payload, list):
                self.received_messages = list(payload)
            else:
                self.received_messages = [payload]
            print(f"Captured {len(self.received_messages)} messages")
            return payload
            
        self.output_pipe.ports.input['pipe_input'].unpack_payload_callback = capture_messages
    
    def tearDown(self):
        """Clean up after each test."""
        print("----- Test completed -----")
        self.received_messages = []
        # Clear any class-level test fixtures if needed
    
    def assert_message_content(self, index, role, content_substring=None, exact_content=None):
        """Helper method to assert message properties."""
        self.assertTrue(index < len(self.received_messages), 
                       f"Expected message at index {index}, but only received {len(self.received_messages)} messages")
        
        msg = self.received_messages[index]
        self.assertEqual(msg.model.role, role, f"Message {index} role mismatch")
        
        if exact_content is not None:
            self.assertEqual(msg.model.content, exact_content, f"Message {index} content mismatch")
            print(f"✓ Message {index} content verified: '{exact_content}'")
        
        if content_substring is not None:
            self.assertIn(content_substring, msg.model.content, 
                         f"Message {index} does not contain expected substring: {content_substring}")
            print(f"✓ Message {index} contains substring: '{content_substring}'")
    
    #-------------------------------------------------------------------
    # Tests for basic message routing
    #-------------------------------------------------------------------
    
    def test_basic_routing(self):
        """Test the most basic message routing without special features."""
        print("\n===== RUNNING TEST: Basic Routing =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Create a minimal context builder
        print("Creating ContextBuilder with emit_order")
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
            # We need to specify either emit_order, trigger_map, or build_fn
            # Using emit_order is the simplest approach
            emit_order=['user_msg', 'assistant_msg'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send messages
        print("Sending user message: 'Hello'")
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        # Only one input provided, not enough for emit_order to trigger
        self.assertEqual(len(self.received_messages), 0, "No messages should be emitted with just one input")
        print("✓ No messages emitted with just one input (as expected)")
        
        print("Sending assistant message: 'Hi there'")
        assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
        
        # Verify output
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} messages (as expected)")
        self.assert_message_content(0, "user", exact_content="Hello")
        self.assert_message_content(1, "assistant", exact_content="Hi there")
    
    #-------------------------------------------------------------------
    # Tests for constants and templates
    #-------------------------------------------------------------------
    
    def test_constants_and_templates(self):
        """Test the basic functionality of constants and templates."""
        print("\n===== RUNNING TEST: Constants and Templates =====")
        # Create input pipe element
        user_input = PipeElement(name="user_input")
        
        # Create a context builder with a constant and template
        print("Creating ContextBuilder with constant and template")
        context_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']]
                },
                'system_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'user_template': {
                    'role': 'system',
                    'template': "The user said: {{ user_msg }}"
                }
            },
            emit_order=[
                'system_constant',
                'user_template',
                'user_msg'
            ],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send a user message
        print("Sending user message: 'How does this work?'")
        user_input.send_payload(MessagePayload(content="How does this work?", role="user"))
        
        # Verify output - should have 3 messages in exact order
        self.assertEqual(len(self.received_messages), 3, "Should receive 3 messages")
        print(f"✓ Received {len(self.received_messages)} messages (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", content_substring="The user said: How does this work?")
        self.assert_message_content(2, "user", exact_content="How does this work?")
    
    #-------------------------------------------------------------------
    # Tests for message control features
    #-------------------------------------------------------------------
    
    def test_emit_order(self):
        """Test the emit_order parameter to control message ordering."""
        print("\n===== RUNNING TEST: Emit Order =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Create a context builder with explicit emit_order
        print("Creating ContextBuilder with explicit emit_order")
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
                'system_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                }
            },
            # Explicitly control the order (system first, then user, then assistant)
            emit_order=[
                'system_constant',
                'user_msg',
                'assistant_msg'
            ],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send both messages to trigger the emit_order
        print("Sending user message: 'What is AI?'")
        user_input.send_payload(MessagePayload(content="What is AI?", role="user"))
        # One input isn't enough to trigger emit_order
        self.assertEqual(len(self.received_messages), 0, "No messages should be emitted yet")
        print("✓ No messages emitted with just one input (as expected)")
        
        print("Sending assistant message: 'AI is artificial intelligence.'")
        assistant_input.send_payload(MessagePayload(content="AI is artificial intelligence.", role="assistant"))
        
        # Verify output - should have 3 messages in exact emit_order
        self.assertEqual(len(self.received_messages), 3, "Should receive 3 messages in emit_order")
        print(f"✓ Received {len(self.received_messages)} messages in correct order (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="What is AI?")
        self.assert_message_content(2, "assistant", exact_content="AI is artificial intelligence.")
    
    def test_trigger_map(self):
        """Test the trigger_map for conditional message emission."""
        print("\n===== RUNNING TEST: Trigger Map =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Create a context builder with trigger_map
        print("Creating ContextBuilder with trigger_map")
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
                },
                'system_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                }
            },
            trigger_map={
                # When user_msg arrives, emit system and user
                'user_msg': ['system_constant', 'user_msg'],
                
                # When assistant_msg arrives, emit all messages in specific order
                'assistant_msg': ['system_constant', 'user_msg', 'assistant_msg']
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Test user message trigger
        print("Sending user message: 'Hello'")
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        
        # Should get system and user message
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} messages from user trigger (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello")
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Test assistant message trigger
        print("Sending assistant message: 'Hi there'")
        assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
        
        # Should get all 3 messages in order
        self.assertEqual(len(self.received_messages), 3, "Should receive 3 messages")
        print(f"✓ Received {len(self.received_messages)} messages from assistant trigger (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello")
        self.assert_message_content(2, "assistant", exact_content="Hi there")
    
    def test_build_fn(self):
        """Test the build_fn for dynamic message building."""
        print("\n===== RUNNING TEST: Build Function =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Define a simple build function
        def custom_build_fn(active_input_port, **kwargs):
            print(f"Build function called with active port: {active_input_port.name}")
            c = kwargs.get('c', {})
            
            if active_input_port.name == 'user_msg':
                # For user messages, just return system and user
                return ['system_constant', 'user_msg']
            elif active_input_port.name == 'assistant_msg':
                # For assistant messages, return all three in reverse order
                return ['assistant_msg', 'user_msg', 'system_constant']
            
            return None
        
        # Create a context builder with build_fn
        print("Creating ContextBuilder with build_fn")
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
                },
                'system_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                }
            },
            build_fn=custom_build_fn,
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Test user message
        print("Sending user message: 'Hello'")
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        
        # Should get system and user message in that order
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} messages from user build_fn (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello")
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Test assistant message - should reverse the order
        print("Sending assistant message: 'Hi there'")
        assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
        
        # Should get all 3 messages in reversed order
        self.assertEqual(len(self.received_messages), 3, "Should receive 3 messages")
        print(f"✓ Received {len(self.received_messages)} messages in reversed order (as expected)")
        self.assert_message_content(0, "assistant", exact_content="Hi there")
        self.assert_message_content(1, "user", exact_content="Hello")
        self.assert_message_content(2, "system", exact_content="You are a helpful assistant.")
    
    #-------------------------------------------------------------------
    # Tests for special features
    #-------------------------------------------------------------------
    
    def test_port_persistence(self):
        """Test that persisted port messages are available for subsequent emissions."""
        print("\n===== RUNNING TEST: Port Persistence =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        context_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True  # User messages should persist
                },
                'assistant_msg': {
                    'role': 'assistant', 
                    'ports': [assistant_input.ports.output['pipe_output']]
                    # No persist flag - should not persist
                }
            },
            emit_order=['user_msg', 'assistant_msg'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send initial messages
        print("Sending initial messages")
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        assistant_input.send_payload(MessagePayload(content="Hi", role="assistant"))
        
        # Clear received messages
        self.received_messages = []
        
        # Send only new assistant message
        print("Sending new assistant message")
        assistant_input.send_payload(MessagePayload(content="How are you?", role="assistant"))
        
        # Should get both persisted user message and new assistant message
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        self.assert_message_content(0, "user", exact_content="Hello")  # Persisted message
        self.assert_message_content(1, "assistant", exact_content="How are you?")  # New message

    def test_template_with_persisted_ports(self):
        """Test that templates can access persisted port messages."""
        print("\n===== RUNNING TEST: Template with Persisted Ports =====")
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
                },
                'summary_template': {
                    'role': 'system',
                    'template': "Last user message: {{ user_msg }}"
                }
            },
            emit_order=['user_msg', 'assistant_msg', 'summary_template'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send initial messages
        print("Sending messages")
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        assistant_input.send_payload(MessagePayload(content="Hi", role="assistant"))
        
        # Clear received messages
        self.received_messages = []
        
        # Send new assistant message - template should use persisted user message
        print("Sending new assistant message")
        assistant_input.send_payload(MessagePayload(content="How are you?", role="assistant"))
        
        # Verify template uses persisted message
        self.assertEqual(len(self.received_messages), 3)
        self.assert_message_content(0, "user", exact_content="Hello")
        self.assert_message_content(1, "assistant", exact_content="How are you?")
        self.assert_message_content(2, "system", content_substring="Last user message: Hello")

    def test_template_processing(self):
        """Test template processing with variables."""
        print("\n===== RUNNING TEST: Template Processing =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Create a context builder with templates
        print("Creating ContextBuilder with templates")
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
                # Simple template using one variable
                'simple_template': {
                    'role': 'system',
                    'template': "User query: {{ user_msg }}"
                },
                # Template with multiple variables
                'conversation_template': {
                    'role': 'system',
                    'template': "Conversation:\nUser: {{ user_msg }}\nAssistant: {{ assistant_msg }}"
                }
            },
            # Use trigger map for testing different scenarios
            trigger_map={
                'user_msg': ['user_msg', 'simple_template'],
                'assistant_msg': ['user_msg', 'assistant_msg', 'conversation_template']
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send a user message
        print("Sending user message: 'What is Python?'")
        user_input.send_payload(MessagePayload(content="What is Python?", role="user"))
        
        # Should get user message and simple template
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} messages from user trigger (as expected)")
        self.assert_message_content(0, "user", exact_content="What is Python?")
        self.assert_message_content(1, "system", content_substring="User query: What is Python?")
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Send an assistant message
        print("Sending assistant message: 'Python is a programming language.'")
        assistant_input.send_payload(MessagePayload(content="Python is a programming language.", role="assistant"))
        
        # Should get user, assistant, and conversation template
        self.assertEqual(len(self.received_messages), 3, "Should receive 3 messages")
        print(f"✓ Received {len(self.received_messages)} messages from assistant trigger (as expected)")
        self.assert_message_content(0, "user", exact_content="What is Python?")
        self.assert_message_content(1, "assistant", exact_content="Python is a programming language.")
        self.assert_message_content(2, "system", content_substring="User: What is Python?")
        self.assert_message_content(2, "system", content_substring="Assistant: Python is a programming language.")
        print("✓ Conversation template rendered correctly with both variables")

    def test_template_waits_for_all(self):
        """Test that a template does not emit until all its dependent ports have payloads."""
        print("\n===== RUNNING TEST: Template Waits For All =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        extra_input = PipeElement(name="extra_input")
        
        # Create a context builder with a template that depends on two ports: user_msg and extra_msg
        context_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'extra_msg': {
                    'role': 'assistant', 
                    'ports': [extra_input.ports.output['pipe_output']],
                    'persist': True
                },
                'dependent_template': {
                    'role': 'system',
                    'template': "Combined: {{ user_msg }} and {{ extra_msg }}"
                }
            },
            emit_order=['user_msg', 'dependent_template'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send only the user message, leaving extra_msg missing
        print("Sending only user message")
        user_input.send_payload(MessagePayload(content="Hello from user", role="user"))
        
        # Since extra_msg is missing, the dependent_template should cause overall emit to abort
        self.assertEqual(len(self.received_messages), 0, "No messages should be emitted as template dependencies are incomplete")
        print("✓ No messages emitted when one template dependency is missing")
        
        # Now send the extra_msg
        print("Sending extra message")
        extra_input.send_payload(MessagePayload(content="Hello from extra", role="assistant"))
        
        # Now, with both messages, emission should happen
        # Expecting 2 messages: user_msg and dependent_template
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages after all dependencies are met")
        print(f"✓ Received {len(self.received_messages)} messages after all template dependencies are met")
        
        # Verify that the dependent template includes both messages
        # The combined template should render something like "Combined: Hello from user and Hello from extra"
        self.assertIn("Hello from user", self.received_messages[1].model.content, "Template should include user message")
        self.assertIn("Hello from extra", self.received_messages[1].model.content, "Template should include extra message")

    def test_callback(self):
        """Test that the port callback is invoked and transforms the payload."""
        print("\n===== RUNNING TEST: Callback Functionality =====")
        # Create an input pipe element
        user_input = PipeElement(name="user_input")
        
        # Define a callback function that appends ' - callback' to the message content
        def transform_callback(payload):
            # Create a new MessagePayload with transformed content
            return MessagePayload(content=payload.model.content + " - callback", role=payload.model.role)
        
        # Create a ContextBuilder with a connected_input_map using the callback
        context_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user',
                    'ports': [user_input.ports.output['pipe_output']],
                    'callback': transform_callback
                }
            },
            emit_order=['user_msg'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send a test message through the user_input pipe
        test_payload = MessagePayload(content="Test message", role="user")
        user_input.send_payload(test_payload)
        
        # Verify that one message is received and its content is transformed
        self.assertEqual(len(self.received_messages), 1, "Should receive 1 message")
        transformed_message = self.received_messages[0]
        self.assertEqual(transformed_message.model.content, "Test message - callback", "Message content should be transformed by the callback")
        self.assertEqual(transformed_message.model.role, "user", "Message role should remain unchanged")
        print("✓ Callback test passed: Payload correctly transformed")

    def test_flow_controller_persistence(self):
        """Test that persistence is properly handled by the flow controller and template storage."""
        print("\n===== RUNNING TEST: Flow Controller Persistence =====")
        # Create input pipe elements
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
                },
                'msg_constant': {
                    'role': 'system',
                    'message': "This is a constant"
                },
                'msg_template': {
                    'role': 'system',
                    'template': "User said: {{ user_msg }}"
                }
            },
            emit_order=['msg_constant', 'user_msg', 'msg_template', 'assistant_msg'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Verify only regular ports are in flow_map
        self.assertIn('user_msg', context_builder.flow_controller.flow_map['input'])
        self.assertIn('assistant_msg', context_builder.flow_controller.flow_map['input'])
        self.assertNotIn('msg_constant', context_builder.flow_controller.flow_map['input'])
        self.assertNotIn('msg_template', context_builder.flow_controller.flow_map['input'])
        
        # Verify constants and templates are in their respective storages
        self.assertIn('msg_constant', context_builder.constants)
        self.assertIn('msg_template', context_builder.templates)
        
        # Send messages
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        assistant_input.send_payload(MessagePayload(content="Hi", role="assistant"))
        
        # Reset received messages
        self.received_messages = []
        
        # Send new assistant message - user message should persist
        assistant_input.send_payload(MessagePayload(content="How are you?", role="assistant"))
        
        # Should still have user message and template due to persistence
        self.assertEqual(len(self.received_messages), 4, "Should receive 4 messages")
        self.assert_message_content(0, "system", exact_content="This is a constant")
        self.assert_message_content(1, "user", exact_content="Hello")
        self.assert_message_content(2, "system", content_substring="User said: Hello")
        self.assert_message_content(3, "assistant", exact_content="How are you?")

    def test_template_storage(self):
        """Test that template storage properly maintains dependencies."""
        print("\n===== RUNNING TEST: Template Storage =====")
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
                'convo_template': {
                    'role': 'system',
                    'template': "Conversation:\nUser: {{ user_msg }}\nAssistant: {{ assistant_msg }}"
                }
            },
            emit_order=['user_msg', 'assistant_msg', 'convo_template'],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send user message
        user_input.send_payload(MessagePayload(content="What is Python?", role="user"))
        
        # Verify template storage has user message
        self.assertIn('convo_template', context_builder.template_storage)
        self.assertIn('user_msg', context_builder.template_storage['convo_template'])
        
        # Send assistant message
        assistant_input.send_payload(MessagePayload(content="Python is a programming language.", role="assistant"))
        
        # Verify template storage has both messages
        self.assertIn('assistant_msg', context_builder.template_storage['convo_template'])
        
        # Verify template rendered correctly
        self.assertEqual(len(self.received_messages), 3, "Should receive 3 messages")
        template_content = self.received_messages[2].model.content
        self.assertIn("User: What is Python?", template_content)
        self.assertIn("Assistant: Python is a programming language.", template_content)

    def test_optional_items(self):
        """Test that items marked with square brackets [like_this] are treated as optional."""
        print("\n===== RUNNING TEST: Optional Items =====")
        
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        optional_input = PipeElement(name="optional_input")
        
        # Create a context builder with optional items
        print("Creating ContextBuilder with optional items in trigger_map and templates")
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
                'optional_msg': {
                    'role': 'user',
                    'ports': [optional_input.ports.output['pipe_output']],
                    'persist': True
                },
                'system_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                # Template with one optional dependency
                'optional_dep_template': {
                    'role': 'system',
                    'template': "Required: {{ user_msg }} - Optional: {{ optional_msg }}"
                },
                # Template with all required dependencies
                'required_template': {
                    'role': 'system',
                    'template': "User: {{ user_msg }} Assistant: {{ assistant_msg }}"
                }
            },
            # Use trigger_map with optional items
            trigger_map={
                # When user_msg arrives, emit with optional items
                'user_msg': [
                    'system_constant', 
                    'user_msg', 
                    '[optional_msg]',  # Optional message
                    '[optional_dep_template]'  # Optional template
                ],
                
                # When assistant_msg arrives, emit with optional template
                'assistant_msg': [
                    'system_constant',
                    'user_msg',
                    'assistant_msg',
                    '[optional_msg]',  # Optional message
                    'required_template'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Test 1: Trigger with user_msg (optional items missing)
        print("Test 1: Trigger with user_msg (optional items missing)")
        user_input.send_payload(MessagePayload(content="Hello", role="user"))
        
        # Should get system and user message (optional items skipped)
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages (optional items skipped)")
        print(f"✓ Received {len(self.received_messages)} messages (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello")
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Test 2: Add the optional message and trigger again
        print("Test 2: Add optional message and trigger with user_msg")
        optional_input.send_payload(MessagePayload(content="Optional content", role="user"))
        user_input.send_payload(MessagePayload(content="Hello again", role="user"))
        
        # Should get system, user, optional, and optional template
        self.assertEqual(len(self.received_messages), 4, "Should receive 4 messages (with optional items)")
        print(f"✓ Received {len(self.received_messages)} messages (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello again")
        self.assert_message_content(2, "user", exact_content="Optional content")
        self.assert_message_content(3, "system", content_substring="Required: Hello again - Optional: Optional content")
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Test 3: Trigger with assistant_msg
        print("Test 3: Trigger with assistant_msg (with previously added optional message)")
        assistant_input.send_payload(MessagePayload(content="Hi there", role="assistant"))
        
        # Should get all items including the optional message
        self.assertEqual(len(self.received_messages), 5, "Should receive 5 messages (with optional message)")
        print(f"✓ Received {len(self.received_messages)} messages (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello again")
        self.assert_message_content(2, "assistant", exact_content="Hi there")
        self.assert_message_content(3, "user", exact_content="Optional content")
        self.assert_message_content(4, "system", content_substring="User: Hello again Assistant: Hi there")
        
        # Reset state
        print("Resetting context builder state")
        self.received_messages = []
        
        # Test 4: Test emit_order with optional items
        print("Test 4: Using emit_order with optional items")
        # Create a new context builder using emit_order instead of trigger_map
        emit_order_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'optional_msg': {
                    'role': 'system',
                    'ports': [optional_input.ports.output['pipe_output']]
                },
                'system_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                }
            },
            # Use emit_order with optional items
            emit_order=[
                'system_constant',
                'user_msg',
                '[optional_msg]'  # Optional message
            ],
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Create a new PipeElement for optional input to ensure it has no payload
        optional_input = PipeElement(name="optional_input_reset")
        
        # Send user message (optional_msg missing)
        user_input.send_payload(MessagePayload(content="Testing emit_order", role="user"))
        
        # Should get system and user message (optional message skipped)
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages (optional item skipped)")
        print(f"✓ Received {len(self.received_messages)} messages (as expected)")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Testing emit_order")

    def test_dependencies_with_optionality(self):
        """Test that dependencies and optional items work together correctly."""
        print("\n===== RUNNING TEST: Dependencies with Optionality =====")
        
        # Create input pipe elements - one for each test case
        user_input = PipeElement(name="user_input")
        history_input = PipeElement(name="history_input")
        tools_input = PipeElement(name="tools_input")
        case1_input = PipeElement(name="case1_input")
        case2_input = PipeElement(name="case2_input")
        case3_input = PipeElement(name="case3_input")
        case4_input = PipeElement(name="case4_input")
        case5_input = PipeElement(name="case5_input")
        case6_input = PipeElement(name="case6_input")
        
        # Create a context builder with both dependencies and optional items
        print("Creating ContextBuilder with dependencies and optional items")
        context_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [history_input.ports.output['pipe_output']],
                    'persist': True
                },
                'tools': {
                    'role': 'system',
                    'ports': [tools_input.ports.output['pipe_output']],
                    'persist': True
                },
                # Add test case ports to trigger specific test scenarios
                'case1_trigger': {
                    'role': 'user',
                    'ports': [case1_input.ports.output['pipe_output']]
                },
                'case2_trigger': {
                    'role': 'user',
                    'ports': [case2_input.ports.output['pipe_output']]
                },
                'case3_trigger': {
                    'role': 'user',
                    'ports': [case3_input.ports.output['pipe_output']]
                },
                'case4_trigger': {
                    'role': 'user',
                    'ports': [case4_input.ports.output['pipe_output']]
                },
                'case5_trigger': {
                    'role': 'user',
                    'ports': [case5_input.ports.output['pipe_output']]
                },
                'case6_trigger': {
                    'role': 'user',
                    'ports': [case6_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_template': {
                    'role': 'system',
                    'template': "History available: {{ history }}",
                    'depends_on': 'history'  # Explicit dependency beyond template variables
                }
            },
            # Test combinations of required/optional items with dependencies
            trigger_map={
                # Case 1: Required items with dependencies
                'case1_trigger': [
                    'main_system_message_constant',
                    'history_template',  # Required + has dependency
                    'history',
                    'user_msg'
                ],
                
                # Case 2: Optional items with dependencies
                'case2_trigger': [
                    'main_system_message_constant',
                    '[history_template]',  # Optional + has dependency
                    'history',  # Make history optional since we're testing without it
                    'user_msg'
                ],
                
                # Case 3: Required template with dependency
                'case3_trigger': [
                    'main_system_message_constant',
                    'history_template',  # Required + has dependency
                    'history',
                    'user_msg'
                ],
                
                # Case 4: Optional template with dependency
                'case4_trigger': [
                    'main_system_message_constant',
                    '[history_template]',  # Optional + has dependency
                    '[history]',           # Make history optional here
                    'user_msg'
                ],
                
                # Case 5: Multiple dependencies - one missing
                'case5_trigger': [
                    'main_system_message_constant',
                    'multiple_dependency_message_constant',  # Required + has multiple dependencies
                    'history',
                    'user_msg'
                ],
                
                # Case 6: Multiple dependencies - all present
                'case6_trigger': [
                    'main_system_message_constant',
                    'multiple_dependency_message_constant',  # Required + has multiple dependencies
                    'history',
                    'tools',
                    'user_msg'
                ],
                
                # Case 7: Real-world message sequence
                'user_msg': [
                    'main_system_message_constant',
                    '[history_template]',  # Optional with dependency
                    '[history]',  # Optional
                    '[tools_system_message_constant]',  # Optional with dependency
                    '[tools]',  # Optional
                    '[multiple_dependency_message_constant]',  # Optional with multiple dependencies
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Create test data
        sample_history = [
            MessagePayload(content="Previous message 1", role="user"),
            MessagePayload(content="Previous response 1", role="user")
        ]
        sample_tools = MessagePayload(content="tool1, tool2, tool3", role="system")
        sample_user_msg = MessagePayload(content="Hello", role="user")
        
        # Load basic data into persistent ports
        user_input.send_payload(sample_user_msg)
        
        # ---------------------------------------------------------------------------
        # Case 1: Required items with dependencies - WITHOUT history (should fail)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 1: Required items with dependencies - WITHOUT history")
        self.received_messages = []
        
        # Trigger case 1 without loading history data
        case1_input.send_payload(MessagePayload(content="Trigger case 1", role="user"))
        
        # Should not emit any messages because history_template is required
        # but has an unsatisfied dependency (history)
        self.assertEqual(len(self.received_messages), 0, 
            "With missing required dependency, no messages should be emitted")
        print("✓ No messages emitted when required dependency is missing (as expected)")
        
        # ---------------------------------------------------------------------------
        # Case 1: Required items with dependencies - WITH history (should succeed)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 1: Required items with dependencies - WITH history")
        self.received_messages = []
        
        # Load history data
        history_input.send_payload(sample_history)
        
        # Trigger case 1 again, now with history data
        case1_input.send_payload(MessagePayload(content="Trigger case 1", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages:")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Now should emit all 5 messages because all dependencies are satisfied
        # (history contains 2 messages that are individually included)
        self.assertEqual(len(self.received_messages), 5, 
            "With satisfied dependencies, all messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages with all dependencies satisfied")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", content_substring="History available:")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 2: Optional items with dependencies - WITHOUT history (should skip optional items)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 2: Optional items with dependencies - WITHOUT history")
        self.received_messages = []
        
        # Create a new ContextBuilderElement for Case 2 to ensure clean state
        # This avoids issues with persisted payloads from previous tests
        case2_context_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [history_input.ports.output['pipe_output']],
                    'persist': True
                },
                'case2_trigger': {
                    'role': 'user',
                    'ports': [case2_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_template': {
                    'role': 'system',
                    'template': "History available: {{ history }}",
                    'depends_on': 'history'  # Explicit dependency beyond template variables
                }
            },
            trigger_map={
                'case2_trigger': [
                    'main_system_message_constant',
                    '[history_template]',  # Optional + has dependency
                    '[history]',  # Make history optional since we're testing without it
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message for the test
        user_input.send_payload(sample_user_msg)
        
        # Trigger case 2 without history
        case2_input.send_payload(MessagePayload(content="Trigger case 2", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 2 WITHOUT history):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should emit messages, but skip the optional items with unsatisfied dependencies
        self.assertEqual(len(self.received_messages), 2, 
            "With missing optional dependency, only required messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages, correctly skipping optional items")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 2: Optional items with dependencies - WITH history (should include optional items)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 2: Optional items with dependencies - WITH history")
        self.received_messages = []
        
        # Load history data
        history_input.send_payload(sample_history)
        
        # Trigger case 2 again, now with history data
        case2_input.send_payload(MessagePayload(content="Trigger case 2", role="user"))
        
        # Now should emit all 5 messages including the optional ones
        # (history contains 2 messages that are individually included)
        self.assertEqual(len(self.received_messages), 5, 
            "With satisfied optional dependencies, all messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages including optional items")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", content_substring="History available:")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 3: Required template with dependency - WITHOUT history (should fail)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 3: Required template with dependency - WITHOUT history")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input = PipeElement(name="fresh_user_input")
        fresh_case3_input = PipeElement(name="fresh_case3_input")
        
        # Create a new ContextBuilderElement without connecting the history port
        case3_without_history_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'case3_trigger': {
                    'role': 'user',
                    'ports': [fresh_case3_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_template': {
                    'role': 'system',
                    'template': "History available: {{ history }}",
                    'depends_on': 'history'  # Explicit dependency beyond template variables
                }
            },
            trigger_map={
                'case3_trigger': [
                    'main_system_message_constant',
                    'history_template',  # Required + has dependency
                    'history',           # This is defined in trigger_map but not in input_map
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message for this test only
        fresh_user_input.send_payload(MessagePayload(content="Hello", role="user"))
        
        # Trigger case 3 without history
        fresh_case3_input.send_payload(MessagePayload(content="Trigger case 3", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 3 WITHOUT history):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should not emit any messages because history_template is required
        # but has an unsatisfied dependency (history)
        self.assertEqual(len(self.received_messages), 0, 
            "With missing required template dependency, no messages should be emitted")
        print("✓ No messages emitted when required template dependency is missing (as expected)")
        
        # ---------------------------------------------------------------------------
        # Case 3: Required template with dependency - WITH history (should succeed)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 3: Required template with dependency - WITH history")
        self.received_messages = []
        
        # Create a new ContextBuilderElement for Case 3 WITH history to ensure clean state
        case3_with_history_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [history_input.ports.output['pipe_output']],
                    'persist': True
                },
                'case3_trigger': {
                    'role': 'user',
                    'ports': [case3_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_template': {
                    'role': 'system',
                    'template': "History available: {{ history }}",
                    'depends_on': 'history'  # Explicit dependency beyond template variables
                }
            },
            trigger_map={
                'case3_trigger': [
                    'main_system_message_constant',
                    'history_template',  # Required + has dependency
                    'history',
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message for the test
        user_input.send_payload(sample_user_msg)
        
        # Load history data
        history_input.send_payload(sample_history)
        
        # Trigger case 3 again, now with history data
        case3_input.send_payload(MessagePayload(content="Trigger case 3", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 3 WITH history):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Now should emit all 5 messages because all dependencies are satisfied
        # (history contains 2 messages that are individually included)
        self.assertEqual(len(self.received_messages), 5, 
            "With satisfied template dependencies, all messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages with template dependency satisfied")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", content_substring="History available:")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 4: Optional template with dependency - WITHOUT history (should skip optional template)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 4: Optional template with dependency - WITHOUT history")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input_case4 = PipeElement(name="fresh_user_input_case4")
        fresh_case4_input = PipeElement(name="fresh_case4_input")
        
        # Create a new ContextBuilderElement without connecting the history port
        case4_without_history_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input_case4.ports.output['pipe_output']],
                    'persist': True
                },
                'case4_trigger': {
                    'role': 'user',
                    'ports': [fresh_case4_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_template': {
                    'role': 'system',
                    'template': "History available: {{ history }}",
                    'depends_on': 'history'  # Explicit dependency beyond template variables
                }
            },
            trigger_map={
                'case4_trigger': [
                    'main_system_message_constant',
                    '[history_template]',  # Optional + has dependency
                    '[history]',           # Make history optional here
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message for this test only
        fresh_user_input_case4.send_payload(MessagePayload(content="Hello", role="user"))
        
        # Trigger case 4 without history
        fresh_case4_input.send_payload(MessagePayload(content="Trigger case 4", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 4 WITHOUT history):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should emit messages, but skip the optional template with unsatisfied dependencies
        self.assertEqual(len(self.received_messages), 2, 
            "With missing optional template dependency, only required messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages, correctly skipping optional template")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 4: Optional template with dependency - WITH history (should include optional template)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 4: Optional template with dependency - WITH history")
        self.received_messages = []
        
        # Create a new ContextBuilderElement with history for Case 4
        case4_with_history_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [history_input.ports.output['pipe_output']],
                    'persist': True
                },
                'case4_trigger': {
                    'role': 'user',
                    'ports': [case4_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_template': {
                    'role': 'system',
                    'template': "History available: {{ history }}",
                    'depends_on': 'history'  # Explicit dependency beyond template variables
                }
            },
            trigger_map={
                'case4_trigger': [
                    'main_system_message_constant',
                    '[history_template]',  # Optional + has dependency
                    '[history]',
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message for the test
        user_input.send_payload(sample_user_msg)
        
        # Load history data
        history_input.send_payload(sample_history)
        
        # Trigger case 4 again, now with history data
        case4_input.send_payload(MessagePayload(content="Trigger case 4", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 4 WITH history):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Now should emit all 5 messages including the optional template
        # (history contains 2 messages that are individually included)
        self.assertEqual(len(self.received_messages), 5, 
            "With satisfied optional template dependency, all messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages including optional template")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", content_substring="History available:")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 5: Multiple dependencies - one missing (should fail)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 5: Multiple dependencies - one missing")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input_case5 = PipeElement(name="fresh_user_input_case5")
        fresh_history_input_case5 = PipeElement(name="fresh_history_input_case5")
        fresh_case5_input = PipeElement(name="fresh_case5_input")
        
        # Create a new ContextBuilderElement with history but no tools
        case5_without_tools_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input_case5.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [fresh_history_input_case5.ports.output['pipe_output']],
                    'persist': True
                },
                'case5_trigger': {
                    'role': 'user',
                    'ports': [fresh_case5_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'multiple_dependency_message_constant': {
                    'role': 'system',
                    'message': "You have both history and tools available.",
                    'depends_on': ['history', 'tools']  # Only included when BOTH are available
                }
            },
            trigger_map={
                'case5_trigger': [
                    'main_system_message_constant',
                    'multiple_dependency_message_constant',  # Required + has multiple dependencies
                    'history',
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message and history for this test
        fresh_user_input_case5.send_payload(MessagePayload(content="Hello", role="user"))
        fresh_history_input_case5.send_payload(sample_history)
        
        # Trigger case 5 with history but no tools
        fresh_case5_input.send_payload(MessagePayload(content="Trigger case 5", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 5 WITH missing dependency):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should not emit any messages because multiple_dependency_message_constant requires both
        # history and tools, but tools is missing
        self.assertEqual(len(self.received_messages), 0, 
            "With one of multiple dependencies missing, no messages should be emitted")
        print("✓ No messages emitted when one of multiple dependencies is missing (as expected)")
        
        # ---------------------------------------------------------------------------
        # Case 6: Multiple dependencies - all present (should succeed)
        # ---------------------------------------------------------------------------
        print("\nTesting Case 6: Multiple dependencies - all present")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input_case6 = PipeElement(name="fresh_user_input_case6")
        fresh_history_input_case6 = PipeElement(name="fresh_history_input_case6")
        fresh_tools_input_case6 = PipeElement(name="fresh_tools_input_case6")
        fresh_case6_input = PipeElement(name="fresh_case6_input")
        
        # Create a new ContextBuilderElement with both history and tools
        case6_with_all_deps_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input_case6.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [fresh_history_input_case6.ports.output['pipe_output']],
                    'persist': True
                },
                'tools': {
                    'role': 'system',
                    'ports': [fresh_tools_input_case6.ports.output['pipe_output']],
                    'persist': True
                },
                'case6_trigger': {
                    'role': 'user',
                    'ports': [fresh_case6_input.ports.output['pipe_output']]
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'multiple_dependency_message_constant': {
                    'role': 'system',
                    'message': "You have both history and tools available.",
                    'depends_on': ['history', 'tools']  # Only included when BOTH are available
                }
            },
            trigger_map={
                'case6_trigger': [
                    'main_system_message_constant',
                    'multiple_dependency_message_constant',  # Required + has multiple dependencies
                    'history',
                    'tools',
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Setup fresh user message, history and tools for this test
        fresh_user_input_case6.send_payload(MessagePayload(content="Hello", role="user"))
        fresh_history_input_case6.send_payload(sample_history)
        fresh_tools_input_case6.send_payload(sample_tools)
        
        # Trigger case 6 with all dependencies satisfied
        fresh_case6_input.send_payload(MessagePayload(content="Trigger case 6", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 6 WITH all dependencies):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Now should emit all 6 messages with multiple dependency item included
        # (history contains 2 messages that are individually included)
        self.assertEqual(len(self.received_messages), 6, 
            "With all multiple dependencies satisfied, all messages should be emitted")
        print(f"✓ Received {len(self.received_messages)} messages with multiple dependencies satisfied")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", exact_content="You have both history and tools available.")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "system", exact_content="tool1, tool2, tool3")
        self.assert_message_content(5, "user", exact_content="Hello")
        
        # ---------------------------------------------------------------------------
        # Case 7: Real-world message sequence - no optional dependencies
        # ---------------------------------------------------------------------------
        print("\nTesting Case 7: Real-world message sequence - no optional dependencies")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input_case7a = PipeElement(name="fresh_user_input_case7a")
        
        # Create a new ContextBuilderElement for real-world scenario without optional deps
        case7a_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input_case7a.ports.output['pipe_output']],
                    'persist': True
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_system_message_constant': {
                    'role': 'system',
                    'message': "The following is a history of our previous interactions.",
                    'depends_on': 'history'  # Only included when history has data
                },
                'tools_system_message_constant': {
                    'role': 'system',
                    'message': "The following are available tools for you to use.",
                    'depends_on': 'tools'  # Only included when tools has data
                },
                'multiple_dependency_message_constant': {
                    'role': 'system',
                    'message': "You have both history and tools available.",
                    'depends_on': ['history', 'tools']  # Only included when BOTH are available
                }
            },
            trigger_map={
                'user_msg': [
                    'main_system_message_constant',
                    '[history_system_message_constant]',  # Optional with dependency
                    '[history]',  # Optional
                    '[tools_system_message_constant]',  # Optional with dependency
                    '[tools]',  # Optional
                    '[multiple_dependency_message_constant]',  # Optional with multiple dependencies
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Trigger with user_msg (no optional dependencies available)
        fresh_user_input_case7a.send_payload(MessagePayload(content="Testing real-world case", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 7 NO optional deps):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should emit only required messages (system constant and user message)
        self.assertEqual(len(self.received_messages), 2, 
            "Real-world case should emit required messages only")
        print(f"✓ Received {len(self.received_messages)} messages in real-world case with no optional dependencies")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "user", exact_content="Testing real-world case")
        
        # ---------------------------------------------------------------------------
        # Case 7: Real-world message sequence - with some optional dependencies
        # ---------------------------------------------------------------------------
        print("\nTesting Case 7: Real-world message sequence - with some optional dependencies")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input_case7b = PipeElement(name="fresh_user_input_case7b")
        fresh_history_input_case7b = PipeElement(name="fresh_history_input_case7b")
        
        # Create a new ContextBuilderElement for real-world scenario with only history
        case7b_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input_case7b.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [fresh_history_input_case7b.ports.output['pipe_output']],
                    'persist': True
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_system_message_constant': {
                    'role': 'system',
                    'message': "The following is a history of our previous interactions.",
                    'depends_on': 'history'  # Only included when history has data
                },
                'tools_system_message_constant': {
                    'role': 'system',
                    'message': "The following are available tools for you to use.",
                    'depends_on': 'tools'  # Only included when tools has data
                },
                'multiple_dependency_message_constant': {
                    'role': 'system',
                    'message': "You have both history and tools available.",
                    'depends_on': ['history', 'tools']  # Only included when BOTH are available
                }
            },
            trigger_map={
                'user_msg': [
                    'main_system_message_constant',
                    '[history_system_message_constant]',  # Optional with dependency
                    '[history]',  # Optional
                    '[tools_system_message_constant]',  # Optional with dependency
                    '[tools]',  # Optional
                    '[multiple_dependency_message_constant]',  # Optional with multiple dependencies
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Add history but not tools
        fresh_history_input_case7b.send_payload(sample_history)
        
        # Trigger with user_msg
        fresh_user_input_case7b.send_payload(MessagePayload(content="Testing real-world case with history", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 7 WITH some optional deps):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should emit system constant, history-related messages, and user message (not tool-related)
        self.assertEqual(len(self.received_messages), 5, 
            "Real-world case should emit messages with available optional dependencies")
        print(f"✓ Received {len(self.received_messages)} messages in real-world case with some optional dependencies")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", exact_content="The following is a history of our previous interactions.")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "user", exact_content="Testing real-world case with history")
        
        # ---------------------------------------------------------------------------
        # Case 7: Real-world message sequence - with all optional dependencies
        # ---------------------------------------------------------------------------
        print("\nTesting Case 7: Real-world message sequence - with all optional dependencies")
        self.received_messages = []
        
        # Create entirely new pipes to ensure no state leakage
        fresh_user_input_case7c = PipeElement(name="fresh_user_input_case7c")
        fresh_history_input_case7c = PipeElement(name="fresh_history_input_case7c")
        fresh_tools_input_case7c = PipeElement(name="fresh_tools_input_case7c")
        
        # Create a new ContextBuilderElement for real-world scenario with all deps
        case7c_builder = ContextBuilderElement(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [fresh_user_input_case7c.ports.output['pipe_output']],
                    'persist': True
                },
                'history': {
                    'payload_type': list[MessagePayload],
                    'ports': [fresh_history_input_case7c.ports.output['pipe_output']],
                    'persist': True
                },
                'tools': {
                    'role': 'system',
                    'ports': [fresh_tools_input_case7c.ports.output['pipe_output']],
                    'persist': True
                },
                'main_system_message_constant': {
                    'role': 'system',
                    'message': "You are a helpful assistant."
                },
                'history_system_message_constant': {
                    'role': 'system',
                    'message': "The following is a history of our previous interactions.",
                    'depends_on': 'history'  # Only included when history has data
                },
                'tools_system_message_constant': {
                    'role': 'system',
                    'message': "The following are available tools for you to use.",
                    'depends_on': 'tools'  # Only included when tools has data
                },
                'multiple_dependency_message_constant': {
                    'role': 'system',
                    'message': "You have both history and tools available.",
                    'depends_on': ['history', 'tools']  # Only included when BOTH are available
                }
            },
            trigger_map={
                'user_msg': [
                    'main_system_message_constant',
                    '[history_system_message_constant]',  # Optional with dependency
                    '[history]',  # Optional
                    '[tools_system_message_constant]',  # Optional with dependency
                    '[tools]',  # Optional
                    '[multiple_dependency_message_constant]',  # Optional with multiple dependencies
                    'user_msg'
                ]
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Add both history and tools
        fresh_history_input_case7c.send_payload(sample_history)
        fresh_tools_input_case7c.send_payload(sample_tools)
        
        # Trigger with user_msg
        fresh_user_input_case7c.send_payload(MessagePayload(content="Testing real-world case with all dependencies", role="user"))
        
        # Debug - print all messages
        print("\nDEBUG - All received messages (Case 7 WITH all optional deps):")
        for i, msg in enumerate(self.received_messages):
            print(f"Message {i}: role={msg.model.role}, content={msg.model.content[:50]}{'...' if len(str(msg.model.content)) > 50 else ''}")
        
        # Should emit all messages including those with multiple dependencies
        self.assertEqual(len(self.received_messages), 8, 
            "Real-world case should emit all messages with all optional dependencies")
        print(f"✓ Received {len(self.received_messages)} messages in real-world case with all optional dependencies")
        self.assert_message_content(0, "system", exact_content="You are a helpful assistant.")
        self.assert_message_content(1, "system", exact_content="The following is a history of our previous interactions.")
        # History messages are included individually
        self.assert_message_content(2, "user", exact_content="Previous message 1")
        self.assert_message_content(3, "user", exact_content="Previous response 1")
        self.assert_message_content(4, "system", exact_content="The following are available tools for you to use.")
        self.assert_message_content(5, "system", exact_content="tool1, tool2, tool3")
        self.assert_message_content(6, "system", exact_content="You have both history and tools available.")
        self.assert_message_content(7, "user", exact_content="Testing real-world case with all dependencies")
        
        print("✓ All dependency and optionality tests completed successfully")

if __name__ == "__main__":
    unittest.main() 