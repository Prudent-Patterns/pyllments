from typing import Union, get_origin, get_args, Any, List, Dict, Awaitable, TypeVar, Generic, Optional
import inspect
import asyncio
from uuid import uuid4
import signal
import weakref

import param
from loguru import logger

from pyllments.base.payload_base import Payload
from pyllments.logging import log_staging, log_emit, log_receive, log_connect
from pyllments.common.loop_registry import LoopRegistry
from pyllments.ports.lifecycle_manager import manager as lifecycle_manager

# Type variable for generic payload types
T = TypeVar('T', bound=Payload)


class Port(param.Parameterized):
    """Base implementation of Port - InputPort and OutputPort inherit from this"""
    payload_type = param.Parameter(doc="The type of payload this port handles")
    connected_elements = param.List(doc="List of elements connected to this port")
    id = param.String(doc="Unique identifier for the port")

    def __init__(self, containing_element=None, **params):
        super().__init__(**params)
        self.containing_element = containing_element
        self.id = str(uuid4())

    def __hash__(self):
        """Return a hash of the component's id for use in hash-based collections."""
        return hash(self.id)

    def __eq__(self, other):
        """Check equality based on the component's id."""
        if not isinstance(other, Port):
            return NotImplemented
        return self.id == other.id
    
    @staticmethod
    def is_payload_compatible(output_type: type, input_type: type) -> bool:
        """
        Checks if the output payload type can be safely received by the input payload type.
        Follows covariance rules for generics like List and Union. Type compatibility
        means that an instance of `output_type` can be safely passed to something
        expecting `input_type`.

        Args:
            output_type: The type annotation of the payload emitted by the output port.
            input_type: The type annotation of the payload expected by the input port.

        Returns:
            bool: True if the types are compatible for connection, False otherwise.
        """
        # Handle Any type - always compatible
        if output_type is Any or input_type is Any:
            return True

        # Identical types are compatible
        if output_type == input_type:
            return True

        origin_output = get_origin(output_type)
        origin_input = get_origin(input_type)
        args_output = get_args(output_type)
        args_input = get_args(input_type)

        # Case 1: Input is Union
        if origin_input is Union:
            # Output must be compatible with *at least one* type in the Input Union.
            # This handles T -> Union[T, U].
            if origin_output is Union:
                # If output is also Union, *all* output types must be compatible
                # with *at least one* input type. This handles Union[T, U] -> Union[T, U, V].
                return all(any(Port.is_payload_compatible(ot, it) for it in args_input)
                           for ot in args_output)
            else:
                # If output is not Union, it must be compatible with *at least one* input type.
                return any(Port.is_payload_compatible(output_type, it) for it in args_input)

        # Case 2: Output is Union (and Input is not Union)
        elif origin_output is Union:
            # *All* types in the Output Union must be compatible with the single Input type.
            # This handles Union[T, U] -> T (only if U is also compatible with T).
            return all(Port.is_payload_compatible(ot, input_type) for ot in args_output)

        # Case 3: Both are Lists
        elif origin_output is list and origin_input is list:
            # List compatibility is covariant: List[Sub] is compatible with List[Super].
            # Compare the element types recursively.
            output_elem_type = args_output[0] if args_output else Any
            input_elem_type = args_input[0] if args_input else Any
            return Port.is_payload_compatible(output_elem_type, input_elem_type)

        # Case 4: One is List, the other is not (and not Any/Union handled above)
        elif (origin_output is list) != (origin_input is list):
            # Direct mismatch between List and non-List types is incompatible.
            return False

        # Case 5: Neither is List nor Union - check non-generic types and other generics
        else:
            # Check for simple non-generic subclass relationship (Output can be subclass of Input)
            if origin_output is None and origin_input is None:
                try:
                    # Must handle non-type elements like TypeVar
                    if isinstance(output_type, type) and isinstance(input_type, type):
                         return issubclass(output_type, input_type)
                    else:
                         return False # Cannot compare non-type elements directly
                except TypeError:
                    # issubclass fails if types are not classes (e.g., primitive types if used)
                    return False # Cannot compare types

            # Check for other generic types (e.g., dict, tuple) - check origin compatibility first
            # This assumes covariance for other generics, which might not always be true.
            # A more robust implementation might need specific handling for different generics.
            elif origin_output is not None and origin_input is not None:
                 try:
                     # Origin check: Output origin must be subclass of Input origin
                     if not issubclass(origin_output, origin_input):
                         return False
                     # TODO: Add recursive check for type arguments compatibility if necessary for other generics
                     # For now, just matching origins if Input is superclass of Output origin
                     return True
                 except TypeError:
                     return False # Cannot compare origins

            # All other cases (e.g., generic vs non-generic that isn't List/Union) are incompatible
            else:
                 return False


class InputPort(Port):
    """
    Asynchronous InputPort that receives payloads and processes them.
    
    The unpacking callback can be either synchronous or asynchronous.
    Sequential processing is ensured for each input port.
    """
    unpack_payload_callback = param.Callable(doc="""
        Callback function that processes incoming payloads.
        Can be a regular function or a coroutine function.""")
    
    def __init__(self, **params):
        super().__init__(**params)
        
        # Cache for validated output ports
        self._validated_output_ports = set()
        
        # Sequential processing lock
        self._processing_lock = asyncio.Lock()
        
        # Connections tracking
        self.output_ports = []
        
        # Infer payload type from callback if not explicitly provided
        if self.unpack_payload_callback and not self.payload_type:
            self._infer_payload_type()
    
    def _infer_payload_type(self):
        """Extract payload type from the callback's signature."""
        sig = inspect.signature(self.unpack_payload_callback)
        params = list(sig.parameters.values())
        
        if not params:
            raise ValueError(f"unpack_payload_callback must have at least one parameter")
            
        first_param = params[0]
        if first_param.annotation is inspect._empty:
            raise ValueError(f"First parameter of unpack_payload_callback must have a type annotation")
            
        self.payload_type = first_param.annotation
    
    async def receive(self, payload: Payload, output_port: 'OutputPort') -> None:
        """
        Process a received payload, ensuring sequential processing.
        
        Args:
            payload: The payload to process
            output_port: The port that emitted the payload
        """
        if not self.unpack_payload_callback:
            raise ValueError(f"unpack_payload_callback must be set for port '{self.name}'")
        
        # Validate payload type if not already validated for this output port
        if output_port not in self._validated_output_ports:
            valid = await self._validate_payload(payload)
            if not valid:
                raise TypeError(f"Incompatible payload type for port '{self.name}'. "
                               f"Expected {self.payload_type}, got {type(payload)}")
            self._validated_output_ports.add(output_port)
        
        # Log reception 
        log_receive(self, payload)
        
        # Process sequentially
        async with self._processing_lock:
            result = self.unpack_payload_callback(payload)
            
            # Handle async callbacks
            if asyncio.iscoroutine(result):
                await result
    
    async def _validate_payload(self, payload) -> bool:
        """
        Validate payload against the expected type, safely handling parameterized generics.
        
        Args:
            payload: The payload to validate
            
        Returns:
            bool: True if the payload is valid for this port, False otherwise
        """
        if self.payload_type is None:
            return True
            
        # Handle Any type
        if self.payload_type is Any:
            return True
            
        # Get origin and args for generic types
        origin = get_origin(self.payload_type)
        args = get_args(self.payload_type)
        
        # Handle Union types (e.g., Union[A, B] or A | B in Python 3.10+)
        if origin is Union:
            for arg_type in args:
                if self._validate_single_type(payload, arg_type):
                    return True
            return False
        
        # Handle List types (e.g., list[MessagePayload])
        if origin is list and isinstance(payload, list):
            # Empty list is valid
            if not payload:
                return True
                
            # If no type args provided, any list is valid
            if not args:
                return True
                
            # Get element type and check each item
            elem_type = args[0]
            
            # Handle union types inside lists
            if get_origin(elem_type) is Union:
                union_types = get_args(elem_type)
                for item in payload:
                    if not any(self._validate_single_type(item, t) for t in union_types):
                        return False
                return True
            else:
                # Check each item against the element type
                for item in payload:
                    if not self._validate_single_type(item, elem_type):
                        return False
                return True
        
        # For other generic types, check against origin
        if origin is not None:
            return isinstance(payload, origin)
            
        # For normal types, do a direct instance check
        return isinstance(payload, self.payload_type)
        
    def _validate_single_type(self, value, expected_type):
        """
        Helper method to validate a single value against a type.
        Handles special type checking cases.
        """
        # Any type is always valid
        if expected_type is Any:
            return True
            
        # Handle generic types
        origin = get_origin(expected_type)
        if origin is not None:
            # For generic types like list, dict, etc.
            if not isinstance(value, origin):
                return False
                
            # Additional checks for specific generic types could be added here
            return True
            
        # For normal types, do a direct instance check
        try:
            return isinstance(value, expected_type)
        except TypeError:
            # Handle cases where isinstance doesn't work with the type
            logger.warning(f"Type check failed for {value} against {expected_type}")
            return False
    
    def __gt__(self, other):
        """Support for the '>' operator to connect ports in reverse."""
        if isinstance(other, OutputPort):
            other.connect(self)
        return self


class OutputPort(Port):
    """
    Asynchronous OutputPort that packs and emits payloads.
    
    Ensures ordered delivery to input ports in the order they were connected.
    Supports both synchronous and asynchronous packing callbacks.
    """
    # Configuration params
    required_items = param.Dict(doc="""
        Dictionary of required items with their types and values.
        Structure: {item_name: {'value': None, 'type': type}}""")
    
    emit_when_ready = param.Boolean(default=True, doc="""
        If true, automatically emit when all required items are staged""")
    
    infer_from_callback = param.Boolean(default=True, doc="""
        Infer required items from pack_payload_callback signature""")
    
    pack_payload_callback = param.Callable(default=None, doc="""
        Callback to pack staged items into a payload.
        Can be a regular function or a coroutine function.""")
    
    on_connect_callback = param.Callable(default=None, doc="""
        Callback executed when a port is connected.
        Can be a regular function or a coroutine function.""")
    
    # State tracking
    emit_ready = param.Boolean(default=False, doc="""
        True when all required items are staged and ready to emit""")
    
    def __init__(self, **params):
        super().__init__(**params)
        
        # Queue for ordered emission processing
        self._emission_queue = asyncio.Queue()
        self._emission_task = None
        
        # Connected input ports in order of connection
        self.input_ports = []
        
        # Process callback annotations
        self._process_callback_annotations()
        
        # Start the emission processor
        self._start_emission_processor()
        
        # Register with the manager
        lifecycle_manager.register_port(self)
    
    def _process_callback_annotations(self):
        """Extract parameter and return types from pack_payload_callback."""
        if not self.pack_payload_callback:
            self.required_items = {'payload': {'value': None, 'type': Any}}
            return
            
        if not self.infer_from_callback:
            if not self.required_items:
                self.required_items = {'payload': {'value': None, 'type': Any}}
            return
        
        annotations = inspect.getfullargspec(self.pack_payload_callback).annotations
        if not annotations:
            raise ValueError("pack_payload_callback must have annotations for inference")
        
        return_annotation = annotations.pop('return', None)
        if return_annotation is None:
            raise ValueError("pack_payload_callback must have a return type annotation")
        
        self.payload_type = return_annotation
        self.required_items = {
            name: {'value': None, 'type': type_}
            for name, type_ in annotations.items()
        }
    
    def _start_emission_processor(self):
        """Start the queue processor task for handling emissions."""
        try:
            loop = LoopRegistry.get_loop()
            self._emission_task = loop.create_task(self._process_emission_queue())
            logger.debug(f"Started emission processor for port {self.name}")
        except Exception as e:
            logger.error(f"Failed to start emission processor: {e}")
    
    async def _process_emission_queue(self):
        """Process emissions in order as they arrive in the queue."""
        try:
            while True:
                emission = await self._emission_queue.get()
                
                try:
                    payload = emission['payload']
                    # Process each input port in the order they were connected
                    for port in self.input_ports:
                        await port.receive(payload, self)
                except Exception as e:
                    logger.error(f"Error processing emission from {self.name}: {e}")
                finally:
                    self._emission_queue.task_done()
        except asyncio.CancelledError:
            logger.debug(f"Emission processor for {self.name} cancelled")
    
    async def connect(self, input_ports):
        """
        Connect this output port to one or more input ports.
        
        Args:
            input_ports: A single InputPort or a list/tuple of InputPorts
        """
        ports_list = input_ports if isinstance(input_ports, (list, tuple)) else [input_ports]
        
        for port in ports_list:
            # Type check
            if not isinstance(port, InputPort):
                raise ValueError(f"Can only connect OutputPorts to InputPorts")
            
            # Payload compatibility check
            if not Port.is_payload_compatible(self.payload_type, port.payload_type):
                raise ValueError(
                    f"Incompatible payload types:\n"
                    f"OutputPort '{self.name}' with type {self.payload_type}\n"
                    f"InputPort '{port.name}' with type {port.payload_type}"
                )
            
            # Add connections
            self.input_ports.append(port)
            port.output_ports.append(self)
            
            # Update connection tracking
            self.connected_elements.append(port.containing_element)
            port.connected_elements.append(self.containing_element)
            
            # Log the connection
            log_connect(self, port)
            
            # Execute connect callback if provided
            if self.on_connect_callback:
                result = self.on_connect_callback(self)
                if asyncio.iscoroutine(result):
                    await result
        
        # For chaining support
        return input_ports if isinstance(input_ports, (list, tuple)) else input_ports
    
    async def stage(self, **kwargs):
        """
        Stage values for later emission.
        
        Args:
            **kwargs: Key-value pairs to stage, matching required_items
        """
        for name, value in kwargs.items():
            # Check if the item is required
            if name not in self.required_items:
                raise ValueError(f"'{name}' is not a required item for port '{self.name}'")
            
            # Type checking
            expected_type = self.required_items[name]['type']
            if expected_type is not Any:
                # Check if value matches expected type
                if not self._check_type(value, expected_type):
                    raise TypeError(f"Value for '{name}' has incorrect type. "
                                  f"Expected {expected_type}, got {type(value)}")
            
            # Store the value
            self.required_items[name]['value'] = value
            
            # Log the staging
            log_staging(self, name, value)
        
        # Check if all required items are staged
        if self._is_ready_to_emit():
            self.emit_ready = True
            
            # Auto-emit if configured
            if self.emit_when_ready:
                await self.emit()
    
    def _check_type(self, value, expected_type):
        """
        Check if a value matches the expected type, safely handling parameterized generics.
        
        This method performs runtime type checking, respecting Python's type annotation
        system even with parameterized generics like list[MessagePayload].
        
        Args:
            value: The value to check
            expected_type: The expected type annotation
            
        Returns:
            bool: True if the value matches the expected type, False otherwise
        """
        # Handle Any type - anything goes
        if expected_type is Any:
            return True
            
        origin = get_origin(expected_type)
        args = get_args(expected_type)
        
        # Handle Union types (e.g., Union[A, B] or A | B in Python 3.10+)
        if origin is Union:
            return any(self._check_type(value, arg_type) for arg_type in args)
        
        # Handle List types (e.g., list[MessagePayload])
        if origin is list:
            # First check if the value is a list
            if not isinstance(value, list):
                return False
            
            # Empty list is valid
            if not value:
                return True
            
            # If we have list element type specs, check each element
            if args:
                elem_type = args[0]
                
                # Handle union types inside lists (e.g., list[Union[A, B]])
                if get_origin(elem_type) is Union:
                    union_types = get_args(elem_type)
                    # Each item must match at least one of the union types
                    for item in value:
                        if not any(self._check_item_type(item, ut) for ut in union_types):
                            return False
                    return True
                else:
                    # Regular list[Type] - check each item against Type
                    return all(self._check_item_type(item, elem_type) for item in value)
            
            # If list has no type args, any list is valid
            return True
            
        # For other generic types, check against the origin type
        if origin is not None:
            return isinstance(value, origin)
            
        # For non-generic types, use regular isinstance
        return isinstance(value, expected_type)
    
    def _check_item_type(self, item, expected_type):
        """
        Helper method to check an individual item's type, handling special cases.
        
        This separates the item-level type checking logic for reusability.
        """
        # Special case for Any
        if expected_type is Any:
            return True
            
        # Handle runtime generics
        origin = get_origin(expected_type)
        if origin is not None:
            # For generic types, first check the origin
            if not isinstance(item, origin):
                return False
                
            # Then handle specific generic patterns as needed
            # (Add specific cases here if needed)
            return True
            
        # For non-generic types, use regular isinstance
        try:
            return isinstance(item, expected_type)
        except TypeError:
            # If isinstance fails (e.g., with a TypeVar), conservatively return False
            logger.warning(f"Type check failed for {item} against {expected_type}")
            return False
            
    def _is_ready_to_emit(self):
        """Check if all required items have been staged."""
        return all(item['value'] is not None for item in self.required_items.values())
    
    async def emit(self):
        """
        Pack the staged values into a payload and emit it to all connected input ports.
        """
        if not self.emit_ready:
            missing_items = [name for name, item in self.required_items.items() 
                           if item['value'] is None]
            raise ValueError(f"Cannot emit from {self.name}: missing required items {missing_items}")
        
        # Pack the payload
        payload = await self._pack_payload()
        
        # Log the emission
        log_emit(self, payload)
        
        # Queue the emission for ordered processing
        await self._emission_queue.put({
            'payload': payload,
            'timestamp': asyncio.get_event_loop().time()
        })
        
        # Reset state
        self.emit_ready = False
        for item in self.required_items.values():
            item['value'] = None
        
        return payload
    
    async def stage_emit(self, **kwargs):
        """
        Stage values and immediately emit a payload.
        
        This is a convenience method that combines stage() and emit().
        """
        await self.stage(**kwargs)
        
        # Only emit if not already emitted by stage() due to emit_when_ready
        if not self.emit_when_ready and self.emit_ready:
            return await self.emit()
        
        return True
    
    async def _pack_payload(self):
        """Pack staged items into a payload using the callback."""
        if not self.pack_payload_callback:
            raise ValueError(f"pack_payload_callback not set for port '{self.name}'")
        
        # Build arguments dict from staged items
        args = {name: item['value'] for name, item in self.required_items.items()}
        
        # Call the callback
        result = self.pack_payload_callback(**args)
        
        # Handle async callbacks
        if asyncio.iscoroutine(result):
            return await result
        
        return result
    
    def __gt__(self, other):
        """Support for the '>' operator to connect ports."""
        loop = LoopRegistry.get_loop()
        loop.create_task(self.connect(other))
        return other

    async def close(self):
        """Perform graceful shutdown of the port, ensuring background task stops."""
        logger.debug(f"Attempting to close port {self.name} ({self.id}).")

        # Cancel the emission processor task and wait for it if possible
        if self._emission_task and not self._emission_task.done():
            self._emission_task.cancel()
            try:
                # Get the loop the task runs on and the current loop
                task_loop = self._emission_task.get_loop()
                current_loop = asyncio.get_running_loop()
                
                # Only await if the task is on the currently running loop and that loop isn't closed
                if task_loop is current_loop and not current_loop.is_closed():
                    logger.debug(f"Waiting for emission task cancellation for port {self.name} on current loop...")
                    # Wait for the task to acknowledge cancellation
                    await asyncio.gather(self._emission_task, return_exceptions=True)
                    logger.debug(f"Emission task for port {self.name} finished cancellation.")
                else:
                    logger.warning(f"Emission task for port {self.name} is on a different or closed loop. Cannot confirm cancellation (expected during atexit). Task Loop ID: {id(task_loop)}, Current Loop ID: {id(current_loop)}")
                    
            except asyncio.CancelledError:
                # This is expected when the task is successfully cancelled on the current loop
                logger.debug(f"Emission task for port {self.name} confirmed cancelled.")
            except Exception as e:
                # Log any other unexpected errors during cancellation
                logger.error(f"Error processing emission task cancellation for port {self.name}: {e}")
        
        self._emission_task = None # Clear the reference

        # Clear connections (safe to do after task is stopped)
        self.input_ports.clear()
        self.connected_elements.clear()
        
        # Reset state
        self.emit_ready = False
        for item in self.required_items.values():
            item['value'] = None
        
        logger.info(f"Port {self.name} ({self.id}) closed successfully.")


class Ports(param.Parameterized):
    """
    Manages input and output ports for an element.
    
    Provides easy access to ports with dot notation:
        element.ports.input_name
        element.ports.output_name
    """
    input = param.Dict(default={}, doc="Dictionary of input ports")
    output = param.Dict(default={}, doc="Dictionary of output ports")
    
    def __init__(self, containing_element=None, **params):
        super().__init__(**params)
        self.containing_element = containing_element
    
    def add_input(self, name: str, unpack_payload_callback, payload_type=None, **kwargs):
        """
        Add an input port.
        
        Args:
            name: Name of the port
            unpack_payload_callback: Function to process incoming payloads
            payload_type: Expected payload type
            **kwargs: Additional parameters for the port
        """
        input_port = InputPort(
            name=name,
            unpack_payload_callback=unpack_payload_callback,
            payload_type=payload_type,
            containing_element=self.containing_element,
            **kwargs
        )
        self.input[name] = input_port
        return input_port
    
    def add_output(self, name: str, pack_payload_callback, payload_type=None, 
                 on_connect_callback=None, **kwargs):
        """
        Add an output port.
        
        Args:
            name: Name of the port
            pack_payload_callback: Function to pack payloads
            payload_type: Type of payload produced
            on_connect_callback: Called when port is connected
            **kwargs: Additional parameters for the port
        """
        output_port = OutputPort(
            name=name,
            pack_payload_callback=pack_payload_callback,
            payload_type=payload_type,
            on_connect_callback=on_connect_callback,
            containing_element=self.containing_element,
            **kwargs
        )
        self.output[name] = output_port
        return output_port
    
    def __getattr__(self, name: str):
        """Enable dot notation access to ports."""
        if name in self.input:
            return self.input[name]
        if name in self.output:
            return self.output[name]
        
        available_ports = list(self.input.keys()) + list(self.output.keys())
        raise AttributeError(f"Port '{name}' not found. Available ports: {available_ports}")
    
    def __setattr__(self, name: str, value):
        """Handle attribute setting with port awareness."""
        if isinstance(value, InputPort):
            self.input[name] = value
        elif isinstance(value, OutputPort):
            self.output[name] = value
        else:
            super().__setattr__(name, value)