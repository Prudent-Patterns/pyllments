import unittest
import logging

from pyllments.elements.transform import TransformElement
from pyllments.elements.pipe import PipeElement
from pyllments.payloads.message import MessagePayload

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestTransformElement(unittest.TestCase):
    """Test suite for TransformElement class."""
    
    def setUp(self):
        """Set up test fixtures for each test."""
        self.received_payloads = []
        
        def capture_payload(payload):
            """Callback function that captures received payloads and logs them."""
            logger.info(f"PipeElement received payload: {payload}")
            logger.info(f"Payload content: {payload.model.content if hasattr(payload, 'model') else 'No content'}")
            self.received_payloads.append(payload)
            return payload
            
        # Create a pipe element with the callback
        self.output_pipe = PipeElement(
            name="output_pipe",
            receive_callback=capture_payload
        )
        logger.info(f"Created output pipe element: {self.output_pipe}")
    
    def tearDown(self):
        """Clean up after each test."""
        self.received_payloads = []
    
    def test_direct_pipe(self):
        """Test direct connection between pipes to validate test setup."""
        logger.info("\n--- Running test_direct_pipe ---")
        
        # Create simple input pipe
        input_pipe = PipeElement(name="test_input")
        logger.info(f"Created input pipe: {input_pipe}")
        
        # Connect directly to output pipe using > operator
        input_pipe.ports.output['pipe_output'] > self.output_pipe.ports.input['pipe_input']
        logger.info("Connected input pipe to output pipe")
        
        # Send a test payload
        logger.info("Sending direct payload")
        test_payload = MessagePayload(content="Direct test", role="user")
        input_pipe.send_payload(test_payload)
        logger.info(f"Sent payload via send_payload: {test_payload}")
        
        # Verify the pipe connection works
        logger.info(f"Direct received payloads: {self.received_payloads}")
        self.assertEqual(len(self.received_payloads), 1, "Should receive direct payload")
        if len(self.received_payloads) > 0:
            self.assertEqual(self.received_payloads[0].model.content, "Direct test")
    
    def test_minimal_transform(self):
        """Minimal test case using input_map."""
        logger.info("\n--- Running test_minimal_transform ---")
        
        # Create input pipe element
        input_pipe = PipeElement(name="input_pipe")
        logger.info(f"Created input pipe: {input_pipe}")
        
        # Define the simplest possible transformation function
        def simple_transform(port_input) -> MessagePayload:
            logger.info(f"simple_transform called with: {port_input.model.content}")
            result = MessagePayload(content=f"Transformed: {port_input.model.content}", role="system")
            logger.info(f"simple_transform returning: {result.model.content}")
            return result
        
        # Create transform element with input_map
        transform = TransformElement(
            name="minimal_transform",
            input_map={
                'port_input': {'payload_type': MessagePayload}
            },
            emit_fn=simple_transform,
            output_payload_type=MessagePayload
        )
        logger.info(f"Created transform element: {transform}")
        
        # Connect ports using > operator
        logger.info("Connecting input_pipe to transform input port")
        input_pipe.ports.output['pipe_output'] > transform.ports.input['port_input']
        
        logger.info("Connecting transform output to output pipe")
        transform.ports.output['transform_output'] > self.output_pipe.ports.input['pipe_input']
        
        # Send a payload to trigger transformation
        logger.info("Sending payload to input_pipe")
        test_payload = MessagePayload(content="Test input", role="user")
        input_pipe.send_payload(test_payload)
        logger.info(f"Sent payload: {test_payload}")
        
        # Verify transformation
        logger.info(f"Received payloads: {self.received_payloads}")
        self.assertEqual(len(self.received_payloads), 1, "Should receive transformed payload")
        if len(self.received_payloads) > 0:
            self.assertEqual(self.received_payloads[0].model.content, "Transformed: Test input")

    def test_connected_ports_in_input_map(self):
        """Test using ports directly in the input_map (replacing connected_input_map)."""
        logger.info("\n--- Running test_connected_ports_in_input_map ---")
        
        # Create input pipe element
        input_pipe = PipeElement(name="input_pipe")
        logger.info(f"Created input pipe: {input_pipe}")
        
        # Define the transformation function
        def simple_transform(port_input) -> MessagePayload:
            logger.info(f"simple_transform called with: {port_input.model.content}")
            result = MessagePayload(content=f"Transformed: {port_input.model.content}", role="system")
            logger.info(f"simple_transform returning: {result.model.content}")
            return result
        
        # Create transform element with ports in input_map (replacing connected_input_map)
        transform = TransformElement(
            name="connected_ports_test",
            input_map={
                'port_input': {
                    'payload_type': MessagePayload,
                    'ports': [input_pipe.ports.output['pipe_output']]
                }
            },
            emit_fn=simple_transform,
            output_payload_type=MessagePayload
        )
        logger.info(f"Created transform element with ports in input_map: {transform}")
        
        # Connect output to pipe using > operator
        logger.info("Connecting transform output to output pipe")
        transform.ports.output['transform_output'] > self.output_pipe.ports.input['pipe_input']
        
        # Send a payload to trigger transformation
        logger.info("Sending payload to input_pipe")
        test_payload = MessagePayload(content="Connected ports test", role="user")
        input_pipe.send_payload(test_payload)
        logger.info(f"Sent payload: {test_payload}")
        
        # Verify transformation
        logger.info(f"Received payloads: {self.received_payloads}")
        self.assertEqual(len(self.received_payloads), 1, "Should receive transformed payload")
        if len(self.received_payloads) > 0:
            self.assertEqual(self.received_payloads[0].model.content, "Transformed: Connected ports test")

    def test_direct_use_of_flow_controller(self):
        """Test using the flow controller's outgoing_input_port parameter."""
        logger.info("\n--- Running test_direct_use_of_flow_controller ---")
        
        # Create transform with direct connection to output pipe
        def transform_fn(input_msg) -> MessagePayload:
            logger.info(f"transform_fn called with: {input_msg.model.content}")
            return MessagePayload(content=f"Transformed: {input_msg.model.content}", role="system")
        
        transform = TransformElement(
            name="flow_controller_test",
            input_map={
                'input_msg': {'payload_type': MessagePayload}
            },
            emit_fn=transform_fn,
            output_payload_type=MessagePayload,
            # Connect directly to output pipe in constructor
            outgoing_input_port=self.output_pipe.ports.input['pipe_input']
        )
        logger.info(f"Created transform element with outgoing port: {transform}")
        
        # Create a source pipe that will send to the transform element
        source_pipe = PipeElement(name="source_pipe")
        logger.info(f"Created source pipe: {source_pipe}")
        
        # Connect source pipe to transform input using > operator
        logger.info("Connecting source pipe to transform input")
        source_pipe.ports.output['pipe_output'] > transform.ports.input['input_msg']
        
        # Send payload via the source pipe
        logger.info("Sending payload via source pipe")
        source_pipe.send_payload(MessagePayload(content="Flow controller test", role="user"))
        
        # Verify transformation
        logger.info(f"Received payloads: {self.received_payloads}")
        self.assertEqual(len(self.received_payloads), 1, "Should receive transformed payload")
        if len(self.received_payloads) > 0:
            self.assertEqual(self.received_payloads[0].model.content, "Transformed: Flow controller test")
    
    def test_emit_fn(self):
        """Test transformation with multiple inputs using emit_fn."""
        logger.info("\n--- Running test_emit_fn ---")
        
        # Create input pipe elements
        input_a = PipeElement(name="input_a")
        input_b = PipeElement(name="input_b")
        logger.info(f"Created input pipes: {input_a}, {input_b}")
        
        # Define transformation function with debug output
        def combine_messages(port_a, port_b) -> MessagePayload:
            logger.info(f"combine_messages called with inputs: {port_a.model.content}, {port_b.model.content}")
            result = MessagePayload(
                content=f"{port_a.model.content} + {port_b.model.content}",
                role="system"
            )
            logger.info(f"combine_messages returning: {result.model.content}")
            return result
        
        # Create transform element with input_map
        transform = TransformElement(
            name="emit_fn_test",
            input_map={
                'port_a': {'payload_type': MessagePayload},
                'port_b': {'payload_type': MessagePayload}
            },
            emit_fn=combine_messages,
            output_payload_type=MessagePayload
        )
        logger.info(f"Created transform element: {transform}")
        
        # Connect input pipes to transform using > operator
        logger.info("Connecting input_a to transform.port_a")
        input_a.ports.output['pipe_output'] > transform.ports.input['port_a']
        
        logger.info("Connecting input_b to transform.port_b")
        input_b.ports.output['pipe_output'] > transform.ports.input['port_b']
        
        # Connect transform output to output pipe
        logger.info("Connecting transform output to output pipe")
        transform.ports.output['transform_output'] > self.output_pipe.ports.input['pipe_input']
        
        # Send test payloads using the send_payload method
        logger.info("Sending payload to input_a")
        input_a.send_payload(MessagePayload(content="Hello", role="user"))
        logger.info("Sent payload to input_a")
        
        logger.info("Sending payload to input_b")
        input_b.send_payload(MessagePayload(content="World", role="assistant"))
        logger.info("Sent payload to input_b")
        
        # Verify output
        logger.info(f"Received payloads: {self.received_payloads}")
        self.assertEqual(len(self.received_payloads), 1, "Should receive exactly one payload")
        if len(self.received_payloads) > 0:
            self.assertEqual(self.received_payloads[0].model.content, "Hello + World")
            self.assertEqual(self.received_payloads[0].model.role, "system")


if __name__ == "__main__":
    unittest.main()
