"""
Asynchronous Ports System for Pyllments

This module provides asynchronous versions of the ports system, maintaining
the same type checking and logging capabilities as the synchronous version.
"""
from typing import Union, get_origin, get_args, Any, Optional, Callable, Dict, List, TypeVar
import inspect
import asyncio
from uuid import uuid4

import param
from loguru import logger

from pyllments.base.payload_base import Payload
from pyllments.logging import log_staging, log_emit, log_receive, log_connect

# Type variable for generic payload types
T = TypeVar('T', bound=Payload)
InputPortT = TypeVar('InputPortT', bound='InputPort')

class AsyncPort(param.Parameterized):
    """Base implementation of asynchronous Port"""
    # Name is set by the containing element
    payload_type = param.Parameter(doc="""
        The type of the payload - set by the unpack_payload_callback or pack_payload_callback""")
    connected_elements = param.List(doc="List of elements connected to this port")
    id = param.String(doc="Unique identifier for the port")

    def __init__(self, containing_element: 'Element' = None, **params):
        super().__init__(**params)
        self.containing_element = containing_element
        self.id = str(uuid4())

    def __hash__(self):
        """Return a hash of the component's id for use in hash-based collections."""
        return hash(self.id)

    def __eq__(self, other):
        """Check equality based on the component's id."""
        if not isinstance(other, AsyncPort):
            return NotImplemented
        return self.id == other.id
    
    @staticmethod
    def is_payload_compatible(output_type: type, input_type: type) -> bool:
        """
        Checks if the output payload type is compatible with the input payload type.
        
        This method handles special cases like Any, Union, and list types.
        """
        # If either type is Any, they're compatible
        if output_type is Any or input_type is Any:
            return True

        # If types are identical, they're compatible
        if output_type == input_type:
            return True

        origin_output = get_origin(output_type)
        origin_input = get_origin(input_type)

        # Handle Union types
        if origin_output is Union:
            return any(AsyncPort.is_payload_compatible(t, input_type) for t in get_args(output_type))
        if origin_input is Union:
            return any(AsyncPort.is_payload_compatible(output_type, t) for t in get_args(input_type))

        # Handle List types
        if origin_output is list and origin_input is list:
            output_elem_type = get_args(output_type)[0]
            input_elem_type = get_args(input_type)[0]
            
            # Handle union types inside lists
            if get_origin(output_elem_type) is Union and get_origin(input_elem_type) is Union:
                # If both are unions, check if any output type is compatible with any input type
                output_union_types = get_args(output_elem_type)
                input_union_types = get_args(input_elem_type)
                return any(any(AsyncPort.is_payload_compatible(ot, it) 
                              for it in input_union_types)
                          for ot in output_union_types)
            elif get_origin(output_elem_type) is Union:
                # If only output is a union, check if any of its types is compatible with input
                return any(AsyncPort.is_payload_compatible(t, input_elem_type) 
                          for t in get_args(output_elem_type))
            elif get_origin(input_elem_type) is Union:
                # If only input is a union, check if output is compatible with any of its types
                return any(AsyncPort.is_payload_compatible(output_elem_type, t) 
                          for t in get_args(input_elem_type))
            else:
                # Regular case - direct compatibility check
                return AsyncPort.is_payload_compatible(output_elem_type, input_elem_type)
            
        if origin_output is list:
            return AsyncPort.is_payload_compatible(get_args(output_type)[0], input_type)
        if origin_input is list:
            return AsyncPort.is_payload_compatible(output_type, get_args(input_type)[0])

        # For non-generic types, use subclass check
        try:
            return issubclass(output_type, input_type)
        except TypeError:
            # If types cannot be used in issubclass, consider them incompatible
            return False


class AsyncInputPort(AsyncPort):
    """Asynchronous InputPort that receives payloads and unpacks them via a callback."""
    output_ports = param.List(doc="Connected output ports")
    unpack_payload_callback = param.Callable(doc="""
        The callback used to unpack the payload - has payload as its only argument.
        Can return a coroutine.""")
    output_ports_validation_map = param.Dict(default={}, doc="""
        Flags whether a payload from the output port has been validated""")

    def __init__(self, **params):
        super().__init__(**params)
        self.output_ports = []
        if self.unpack_payload_callback:
            self._infer_payload_type()
            
        # Track ongoing processing
        self._processing_lock = asyncio.Lock()
        self._active_processing = None

    def _infer_payload_type(self):
        """Extract payload type from unpack_payload_callback signature."""
        sig = inspect.signature(self.unpack_payload_callback)
        params = list(sig.parameters.values())
        if not params:
            raise ValueError(f"unpack_payload_callback must have at least one parameter")
            
        first_param = params[0]
        if first_param.annotation is inspect._empty:
            raise ValueError(f"First parameter of unpack_payload_callback for {self.name} must have a type annotation")
            
        self.payload_type = first_param.annotation

    async def receive(self, payload: Payload, output_port: 'AsyncOutputPort'):
        """Process a received payload, ensuring sequential processing."""
        if not self.unpack_payload_callback:
            raise ValueError(f"unpack_payload_callback must be set for port '{self.name}'")
            
        # Skip validation if already validated
        if output_port not in self.output_ports_validation_map or not self.output_ports_validation_map[output_port]:
            if not await self._validate_payload(payload):
                raise TypeError(f"Incompatible payload type for port '{self.name}'. "
                                f"Expected {self.payload_type}, got {type(payload)}")
                
        # Log reception with same format as the original sync version
        log_receive(self, payload)
        
        # Process sequentially with a lock
        async with self._processing_lock:
            try:
                # Call the callback
                result = self.unpack_payload_callback(payload)
                
                # Handle async callbacks
                if asyncio.iscoroutine(result):
                    await result
                    
                # Mark as validated
                self.output_ports_validation_map[output_port] = True
                logger.debug(f"Completed processing in {self.name}")
            except Exception as e:
                logger.error(f"Error processing in {self.name}: {e}")
                raise

    async def _validate_payload(self, payload) -> bool:
        """
        Validates if the payload is compatible with the port's payload_type.
        """
        if self.payload_type is None:
            return True  # If no type is specified, accept any payload

        async def validate_type(payload, expected_type):
            origin = get_origin(expected_type)
            args = get_args(expected_type)

            if origin is Union:
                results = [await validate_type(payload, arg) for arg in args]
                return any(results)
            elif origin is list:
                if not isinstance(payload, list):
                    raise ValueError(f"For port '{self.name}', payload is not a list. "
                                     f"Expected a list of {get_args(expected_type)[0]}")
                if not payload:
                    raise ValueError(f"For port '{self.name}', payload is an empty list. "
                                     f"Expected a non-empty list of {get_args(expected_type)[0]}")
                
                # Extract the inner type from the list
                inner_type = args[0]
                
                # Handle union types inside lists
                if get_origin(inner_type) is Union:
                    # Get all allowed types from the union
                    allowed_types = get_args(inner_type)
                    # Check if each item in the list is an instance of at least one allowed type
                    if not all(any(isinstance(item, t) for t in allowed_types) for item in payload):
                        type_names = ", ".join(t.__name__ for t in allowed_types)
                        raise ValueError(f"For port '{self.name}', payload contains items "
                                       f"that are not instances of any of: {type_names}")
                else:
                    # Original case - single type checking
                    if not all(isinstance(item, inner_type) for item in payload):
                        raise ValueError(f"For port '{self.name}', payload contains items "
                                       f"that are not instances of {inner_type}")
                
                return True  # If we've passed all checks for list type
            else:
                return isinstance(payload, expected_type)
            
        return await validate_type(payload, self.payload_type)


class AsyncOutputPort(AsyncPort):
    """
    Handles the intake of data and packing into a payload asynchronously,
    ensuring sequential processing and proper type checking.
    """
    required_items = param.Dict(doc="""
        Dictionary of required items with their types and values.
        Structure: {item_name: {'value': None, 'type': type}}""")

    emit_when_ready = param.Boolean(default=True, doc="""
        If true, the payload will be emitted when the required items are staged""")

    emit_ready = param.Boolean(default=False, doc="""
        True when the required items have been staged and the payload can be emitted""")

    infer_from_callback = param.Boolean(default=True, doc="""
        If true, infers the required items from pack_payload_callback
        and required_items is set to None""")

    input_ports = param.List(doc="""
        The connected InputPorts which emit() will contact, in order of connection""")

    pack_payload_callback = param.Callable(default=None, doc="""
        The callback used to create the payload. Can return a coroutine.""")
        
    staged_items = param.List(item_type=str, doc="""
        The items that have been staged and are awaiting emission""")
    
    type_checking = param.Boolean(default=False, doc="""
        If true, type-checking is enabled. Uses a single pass for efficiency.""")
    
    type_check_successful = param.Boolean(default=False, doc="""
        Is set to True once a single type-check has been completed successfully""")
    
    on_connect_callback = param.Callable(default=None, doc="""
        A callback that is called when the port is connected to an input port.
        Can return a coroutine.""")

    def __init__(self, **params: param.Parameter):
        super().__init__(**params)
        
        # Initialize emission queue and task
        self._emission_queue = asyncio.Queue()
        self._emission_task = None
        self._emission_processing = False
        
        # Process callback annotations
        if self.pack_payload_callback and self.infer_from_callback:
            self._process_callback_annotations()
        elif self.required_items and isinstance(next(iter(self.required_items)), dict):
            self.type_checking = True
        elif self.required_items:
            self.required_items = {item: {'value': None, 'type': Any} for item in self.required_items}
        else:
            # If no required_items are specified, assume a single 'payload' item of Any type
            self.required_items = {'payload': {'value': None, 'type': Any}}
            self.type_checking = False

    def _process_callback_annotations(self):
        """Extract parameter and return types from pack_payload_callback."""
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
        self.type_checking = True

    async def connect(self, input_ports: Union['AsyncInputPort', list['AsyncInputPort']]):
        """Connect this output port to one or more input ports in the specified order."""
        ports_list = input_ports if isinstance(input_ports, list) else [input_ports]
        
        for port in ports_list:
            # Validate port type
            if not isinstance(port, AsyncInputPort):
                raise ValueError(f"Can only connect OutputPorts to InputPorts. "
                               f"Attempted to connect '{self.name}' to '{port.name}' ({type(port).__name__})")
            
            # Validate payload compatibility
            if not AsyncPort.is_payload_compatible(self.payload_type, port.payload_type):
                raise ValueError(
                    f"InputPort and OutputPort payload types are not compatible:\n"
                    f"OutputPort '{self.name}' in element '{self.containing_element.__class__.__name__}' "
                    f"with payload type {self.payload_type}\n"
                    f"InputPort '{port.name}' in element '{port.containing_element.__class__.__name__}' "
                    f"with payload type {port.payload_type}"
                )
            
            # Add to ordered list maintaining the exact same connections as in original
            self.input_ports.append(port)
            self.connected_elements.append(port.containing_element)
            port.connected_elements.append(self.containing_element)
            port.output_ports.append(self)
            port.output_ports_validation_map[self] = False
            
            # Log the connection with same format as original
            log_connect(self, port)
            
            # Execute connect callback if provided
            if self.on_connect_callback:
                result = self.on_connect_callback(self)
                if asyncio.iscoroutine(result):
                    await result
            
            # Start emission processor if not running
            if not self._emission_processing:
                self._emission_task = asyncio.create_task(self._process_emission_queue())
                
        # For operator overloading convenience
        return input_ports if isinstance(input_ports, list) else input_ports

    async def _process_emission_queue(self):
        """Process emissions in order from the queue."""
        self._emission_processing = True
        try:
            while True:
                # Get next payload from the queue
                payload_data = await self._emission_queue.get()
                try:
                    # Process ports in order
                    for port in self.input_ports:
                        await port.receive(payload_data['payload'], self)
                except Exception as e:
                    logger.error(f"Error processing emission from {self.name}: {e}")
                finally:
                    self._emission_queue.task_done()
        except asyncio.CancelledError:
            logger.debug(f"Emission queue processor for {self.name} cancelled")
        finally:
            self._emission_processing = False
            self._emission_task = None

    async def stage(self, bypass_type_check: bool = False, **kwargs):
        """Stage data for emission, with the same type checking as original."""
        for name, value in kwargs.items():
            if name not in self.required_items:
                raise ValueError(f"'{name}' is not a required item for port '{self.name}'")
                
            # Maintain the same detailed type checking as original
            if self.type_checking and not bypass_type_check:
                expected_type = self.required_items[name]['type']
                if expected_type is not Any:
                    if get_origin(expected_type) is Union:
                        if not any(isinstance(value, t) for t in get_args(expected_type)):
                            raise ValueError(f"For port '{self.name}', item '{name}' with value '{value}' "
                                             f"is not an instance of any type in {expected_type}")
                    elif get_origin(expected_type) is list:
                        if not isinstance(value, list):
                            raise ValueError(f"For port '{self.name}', item '{name}' with value '{value}' "
                                             f"is not a list")
                        if not value:
                            raise ValueError(f"For port '{self.name}', item '{name}' is an empty list. "
                                             f"Expected a non-empty list of {get_args(expected_type)[0]}")
                        
                        # Get the inner type to check list contents
                        inner_type = get_args(expected_type)[0]
                        
                        # Handle union types inside lists
                        if get_origin(inner_type) is Union:
                            # Get all allowed types from the union
                            allowed_types = get_args(inner_type)
                            # Check if each item in the list is an instance of at least one allowed type
                            if not all(any(isinstance(item, t) for t in allowed_types) for item in value):
                                type_names = ", ".join(t.__name__ for t in allowed_types)
                                raise ValueError(f"For port '{self.name}', item '{name}' contains items "
                                               f"that are not instances of any of: {type_names}")
                        else:
                            # Original case - single type checking
                            if not all(isinstance(item, inner_type) for item in value):
                                raise ValueError(f"For port '{self.name}', item '{name}' contains items "
                                               f"that are not instances of {inner_type}")
                    elif not isinstance(value, expected_type):
                        raise ValueError(f"For port '{self.name}', item '{name}' with value '{value}' "
                                         f"is not an instance of {expected_type}")
                        
            # Store the value
            self.required_items[name]['value'] = value
            
            # Log staging with same format as original
            log_staging(self, name, value)
        
        # Check if ready to emit
        if self._emit_ready_check():
            self.emit_ready = True
            
        # Auto-emit if configured
        if self.emit_when_ready and self.emit_ready:
            await self.emit()

    async def emit(self):
        """Pack the payload and queue it for ordered emission to input ports."""
        if not self.emit_ready:
            raise ValueError(f"Emit failed for port '{self.name}' in element '{type(self.containing_element).__name__}': "
                             f"Not all required items have been staged. "
                             f"Required items: {list(self.required_items.keys())}. "
                             f"Staged items: {[name for name, item in self.required_items.items() if item['value'] is not None]}. "
                             "Please ensure all required items are staged before emitting.")
        
        # Pack the payload
        packed_payload = await self._pack_payload()
        
        # Log emission with same format as original
        log_emit(self, packed_payload)
        
        # Queue the emission for processing
        await self._emission_queue.put({
            'payload': packed_payload,
            'timestamp': asyncio.get_event_loop().time()
        })
        
        # Reset state
        self.emit_ready = False
        self.staged_items = []
        for item in self.required_items.values():
            item['value'] = None
            
        return packed_payload

    async def stage_emit(self, bypass_type_check: bool = False, **kwargs):
        """Stage and immediately emit."""
        await self.stage(bypass_type_check=bypass_type_check, **kwargs)
        if not self.emit_when_ready:  # Only if auto-emit is disabled
            await self.emit()

    async def _pack_payload(self):
        """Pack staged items into a payload, handling async callbacks."""
        if not self.pack_payload_callback:
            raise ValueError(f"pack_payload_callback must be set for port '{self.name}'")
            
        # Build arguments dict from staged items
        staged_dict = {
            name: item['value'] 
            for name, item in self.required_items.items()
        }
        
        # Call the callback
        result = self.pack_payload_callback(**staged_dict)
        
        # Handle both sync and async results
        if asyncio.iscoroutine(result):
            return await result
        return result

    def __gt__(self, other):
        """Support the > operator for port connection."""
        # Create a task for the connection since we can't use await in operator
        asyncio.create_task(self.connect(other))
        return other

    def _emit_ready_check(self):
        """Check if all required items have been staged."""
        ready = all(item['value'] is not None for item in self.required_items.values())
        if ready:
            self.type_check_successful = True
        return ready


class AsyncPorts(param.Parameterized):
    """Keeps track of AsyncInputPorts and AsyncOutputPorts and handles their creation"""
    input = param.Dict(default={}, doc="Dictionary to store input ports")
    output = param.Dict(default={}, doc="Dictionary to store output ports")

    def __init__(self, containing_element=None, **params):
        super().__init__(**params)
        self.containing_element = containing_element

    def add_input(self, name: str, unpack_payload_callback, **kwargs):
        """Add an AsyncInputPort with a callback to unpack payloads."""
        input_port = AsyncInputPort(
            name=name,
            unpack_payload_callback=unpack_payload_callback,
            containing_element=self.containing_element,
            **kwargs)
        self.input[name] = input_port
        return input_port
    
    def add_output(self, name: str, pack_payload_callback, on_connect_callback=None, **kwargs):
        """Add an AsyncOutputPort with callbacks to pack and optionally handle connections."""
        output_port = AsyncOutputPort(
            name=name,
            pack_payload_callback=pack_payload_callback,
            containing_element=self.containing_element,
            on_connect_callback=on_connect_callback,
            **kwargs)
        self.output[name] = output_port
        return output_port

    def __getattr__(self, name: str):
        """Enable dot notation access to ports."""
        # First check if it's in input ports
        if name in self.input:
            return self.input[name]
        # Then check output ports
        elif name in self.output:
            return self.output[name]
        # If not found in either, raise a descriptive error
        available_ports = list(self.input.keys()) + list(self.output.keys())
        raise AttributeError(
            f"Port '{name}' not found. Available ports: {available_ports}"
        )

    def __setattr__(self, name: str, value):
        """Handle attribute setting while preserving dot notation access for ports."""
        if isinstance(value, AsyncInputPort):
            self.input[name] = value
        elif isinstance(value, AsyncOutputPort):
            self.output[name] = value
        else:
            super().__setattr__(name, value) 