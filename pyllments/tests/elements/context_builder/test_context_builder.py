import param
from pyllments.elements import ContextBuilder, PipeElement
from pyllments.payloads import MessagePayload
import unittest

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
            
        self.output_pipe.receive_callback = capture_messages
    
    def tearDown(self):
        """Clean up after each test."""
        print("----- Test completed -----")
        self.received_messages = []
    
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
        context_builder = ContextBuilder(
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
        context_builder = ContextBuilder(
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
        context_builder = ContextBuilder(
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
        context_builder = ContextBuilder(
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
        context_builder = ContextBuilder(
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
        """Test port persistence behavior."""
        print("\n===== RUNNING TEST: Port Persistence =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Create a context builder with one persistent port
        print("Creating ContextBuilder with persistent user port")
        context_builder = ContextBuilder(
            input_map={
                'user_msg': {
                    'role': 'user', 
                    'ports': [user_input.ports.output['pipe_output']],
                    'persist': True  # User messages should persist
                },
                'assistant_msg': {
                    'role': 'assistant', 
                    'ports': [assistant_input.ports.output['pipe_output']]
                    # No persist flag, assistant messages should NOT persist
                }
            },
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        
        # Send initial messages
        print("Sending initial user message: 'Question 1'")
        user_input.send_payload(MessagePayload(content="Question 1", role="user"))
        print("Sending initial assistant message: 'Answer 1'")
        assistant_input.send_payload(MessagePayload(content="Answer 1", role="assistant"))
        
        # Verify both messages were emitted
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} initial messages (as expected)")
        self.assert_message_content(0, "user", exact_content="Question 1")
        self.assert_message_content(1, "assistant", exact_content="Answer 1")
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Send only a new assistant message, user message should persist
        print("Sending only new assistant message: 'Answer 2'")
        assistant_input.send_payload(MessagePayload(content="Answer 2", role="assistant"))
        
        # Verify user message persisted
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} messages with persisted user message (as expected)")
        self.assert_message_content(0, "user", exact_content="Question 1")  # Persisted
        print("✓ User message persisted correctly")
        self.assert_message_content(1, "assistant", exact_content="Answer 2")  # New
        
        # Reset received messages
        print("Resetting received messages")
        self.received_messages = []
        
        # Send a new user message and assistant message
        print("Sending new user message: 'Question 2'")
        user_input.send_payload(MessagePayload(content="Question 2", role="user"))
        print("Sending new assistant message: 'Answer 3'")
        assistant_input.send_payload(MessagePayload(content="Answer 3", role="assistant"))
        
        # Verify updated messages
        self.assertEqual(len(self.received_messages), 2, "Should receive 2 messages")
        print(f"✓ Received {len(self.received_messages)} updated messages (as expected)")
        self.assert_message_content(0, "user", exact_content="Question 2")  # Updated
        print("✓ User message updated correctly")
        self.assert_message_content(1, "assistant", exact_content="Answer 3")  # New
    
    def test_template_processing(self):
        """Test template processing with variables."""
        print("\n===== RUNNING TEST: Template Processing =====")
        # Create input pipe elements
        user_input = PipeElement(name="user_input")
        assistant_input = PipeElement(name="assistant_input")
        
        # Create a context builder with templates
        print("Creating ContextBuilder with templates")
        context_builder = ContextBuilder(
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
        context_builder = ContextBuilder(
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
        context_builder = ContextBuilder(
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

if __name__ == "__main__":
    unittest.main() 