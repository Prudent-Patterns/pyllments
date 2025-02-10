from typing import Union, get_origin, get_args, Any
import inspect
from uuid import uuid4

import param

from pyllments.base.payload_base import Payload
from pyllments.logging import log_staging, log_emit, log_receive, log_connect


class Port(param.Parameterized):
    """Base implementation of Port - InputPort and OutputPort inherit from this"""
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
        if not isinstance(other, Port):
            return NotImplemented
        return self.id == other.id
    

class InputPort(Port):
    output_ports = param.List(item_type=Port)
    unpack_payload_callback = param.Callable(doc="""
        The callback used to unpack the payload - has payload as its only argument.
        Unpacks the payload and connects it to the element's model""")
    output_ports_validation_map = param.Dict(default={}, doc="""
        Flags whether a payload from the output port has been validated""")

    def __init__(self, **params):
        super().__init__(**params)
        if self.unpack_payload_callback:
            # Expects only one annotated argument
            payload_type = next(iter(inspect.signature(self.unpack_payload_callback).parameters.values())).annotation
            if payload_type is inspect._empty:
                raise ValueError(f"unpack_payload_callback must have a return type annotation for port '{self.name}'")
            
            self.payload_type = payload_type

    def receive(self, payload: Payload, output_port: 'OutputPort'):
        if not self.unpack_payload_callback:
            raise ValueError(f"unpack_payload_callback must be set for port '{self.name}'")
        # Check if the incoming payload is compatible with the payload_type
        if output_port not in self.output_ports_validation_map:
            if not self._validate_payload(payload):
                raise TypeError(f"Incompatible payload type for port '{self.name}'. "
                                f"Expected {self.payload_type}, got {type(payload)}")
        log_receive(self, payload)
        self.unpack_payload_callback(payload)
        self.output_ports_validation_map[output_port] = True


    def _validate_payload(self, payload):
        """
        Validates if the payload is compatible with the port's payload_type.
        """
        if self.payload_type is None:
            return True  # If no type is specified, accept any payload


        def validate_type(payload, expected_type):
            origin = get_origin(expected_type)
            args = get_args(expected_type)

            if origin is Union:
                return any(validate_type(payload, arg) for arg in args)
            elif origin is list:
                if not isinstance(payload, list):
                    raise ValueError(f"For port '{self.name}', payload is not a list. "
                                     f"Expected a list of {get_args(expected_type)[0]}")
                if not payload:
                    raise ValueError(f"For port '{self.name}', payload is an empty list. "
                                     f"Expected a non-empty list of {get_args(expected_type)[0]}")
                if not all(isinstance(item, get_args(expected_type)[0]) for item in payload):
                    raise ValueError(f"For port '{self.name}', payload contains items "
                                     f"that are not instances of {get_args(expected_type)[0]}")
                return True  # If we've passed all checks for list type
            else:
                return isinstance(payload, expected_type)
            
        return validate_type(payload, self.payload_type)



class OutputPort(Port):
    """
    Handles the intake of data and packing into a payload and
    is meant to connect to an InputPort in order to emit the packed payload
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

    input_ports = param.List(item_type=InputPort, doc="""
        The connected InputPorts which emit() will contact""")

    pack_payload_callback = param.Callable(default=None, doc="""
        The callback used to create the payload. When used in conjunction with
        infer_required_items == True, an annotated callback can replace passing in
        a payload and required_items while enabling type-checking.
        Kwargs, their types, and the return type are required annotations.""")
        
    staged_items = param.List(item_type=str, doc="""
        The items that have been staged and are awaiting emission""")
    
    type_checking = param.Boolean(default=False, doc="""
        If true, type-checking is enabled. Uses a single pass for efficiency.""")
    
    type_check_successful = param.Boolean(default=False, doc="""
        Is set to True once a single type-check has been completed successfully""")
    

    def __init__(self, **params: param.Parameter):
        super().__init__(**params)

        if self.pack_payload_callback and self.infer_from_callback:
            annotations = inspect.getfullargspec(self.pack_payload_callback).annotations
            if not annotations:
                raise ValueError("pack_payload_callback must have annotations if infer_from_callback is True")
            
            return_annotation = annotations.pop('return', None)
            if return_annotation is None:
                raise ValueError("pack_payload_callback must have a return type annotation")
            
            self.payload_type = return_annotation
            self.required_items = {
                name: {'value': None, 'type': type_}
                for name, type_ in annotations.items()
            }
            self.type_checking = True
        elif self.required_items and isinstance(next(iter(self.required_items)), dict):
            self.type_checking = True
        elif self.required_items:
            self.required_items = {item: {'value': None, 'type': Any} for item in self.required_items}
        else:
            # If no required_items are specified, assume a single 'payload' item of Any type
            self.required_items = {'payload': {'value': None, 'type': Any}}
            self.type_checking = False

    def connect(self, input_ports: Union[InputPort, tuple[InputPort], list[InputPort]]):
        """Connects self and the other InputPort(s)"""
        
        is_iterable = isinstance(input_ports, (tuple, list))
        def _port_check(input_port: InputPort):
            """
            Checks if the individual port is an InputPort
            and if output_type is compatible with input_type.
            """
            if not isinstance(input_port, InputPort):
                raise ValueError(f"Can only connect OutputPorts to InputPorts. "
                            f"Attempted to connect '{self.name}' ({type(self).__name__}) "
                            f"to '{input_port.name}' ({type(input_port).__name__})")
            
            def _is_compatible(output_type, input_type):                
                # If either type is Any, they're compatible
                if output_type is Any or input_type is Any:
                    return True
                
                # If types are identical, they're compatible
                if output_type == input_type:
                    return True
                
                # Handle Union types
                if get_origin(output_type) is Union:
                    return any(_is_compatible(t, input_type) for t in get_args(output_type))
                if get_origin(input_type) is Union:
                    return any(_is_compatible(output_type, t) for t in get_args(input_type))
                
                # Handle List types
                if get_origin(output_type) is list and get_origin(input_type) is list:
                    return _is_compatible(get_args(output_type)[0], get_args(input_type)[0])
                
                # Handle case where one is a List and the other is not
                if get_origin(output_type) is list:
                    return _is_compatible(get_args(output_type)[0], input_type)
                if get_origin(input_type) is list:
                    return _is_compatible(output_type, get_args(input_type)[0])
                
                # Check for subclass relationship for non-generic types
                try:
                    result = issubclass(output_type, input_type)
                    return result
                except TypeError as e:
                    print(f"TypeError in subclass check. output_type: {output_type}, input_type: {input_type}",
                          f"\n\n{e}")
                    return False
            
            # Actually call _is_compatible with the payload types
            compatibility_result = _is_compatible(self.payload_type, input_port.payload_type)
        
            return compatibility_result
        
        # Connect each InputPort in the iterable
        for port in (input_ports if is_iterable else (input_ports,)):
            # Check payload compatibility
            if not _port_check(port):
                raise ValueError(f"""InputPort and OutputPort payload types are not compatible:
                    OutputPort '{self.name}' in element '{self.containing_element.__class__.__name__}' 
                    with payload type {self.payload_type}
                    InputPort '{port.name}' in element '{port.containing_element.__class__.__name__}' 
                    with payload type {port.payload_type}""")
            
            self.input_ports.append(port)
            self.connected_elements.append(port.containing_element)
            port.connected_elements.append(self.containing_element)
            port.output_ports.append(self)
            port.output_ports_validation_map[self] = False
            log_connect(self, port)
        if not is_iterable:
            return input_ports

    def stage(self, bypass_type_check: bool = False, **kwargs):
        """Stages the values within the port before packing"""
        for name, value in kwargs.items():
            if name not in self.required_items:
                raise ValueError(f"'{name}' is not a required item for port '{self.name}'")
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
                        if not all(isinstance(item, get_args(expected_type)[0]) for item in value):
                            raise ValueError(f"For port '{self.name}', item '{name}' contains items "
                                             f"that are not instances of {get_args(expected_type)[0]}")
                    elif not isinstance(value, expected_type):
                        raise ValueError(f"For port '{self.name}', item '{name}' with value '{value}' "
                                         f"is not an instance of {expected_type}")
            self.required_items[name]['value'] = value
            
            # Log each individual staged item
            log_staging(self, name, value)

        if self._emit_ready_check():
            self.emit_ready = True
        
        if self.emit_when_ready and self.emit_ready:
            self.emit()

    def emit(self):
        """Packs the payload and emits it to all registered observers"""
        if not self.emit_ready:
            raise ValueError(f"Emit failed for port '{self.name}' in element '{type(self.containing_element).__name__}': "
                             f"Not all required items have been staged. "
                             f"Required items: {list(self.required_items.keys())}. "
                             f"Staged items: {[name for name, item in self.required_items.items() if item['value'] is not None]}. "
                             "Please ensure all required items are staged before emitting.")
        else:
            packed_payload = self.pack_payload()        
        # Log the element name, port name, and type of payload being emitted
        log_emit(self, packed_payload)
        for port in self.input_ports:
            port.receive(packed_payload, self)
        
        # Reset emit_ready and staged_items after emission
        self.emit_ready = False
        self.staged_items = []
        
        # Reset the values in required_items
        for item in self.required_items.values():
            item['value'] = None
        
        # For returning the payload to the caller 
        return packed_payload
    
    def stage_emit(self, bypass_type_check: bool = False, **kwargs):
        """Stages the payload and emits it - All required params need be present"""
        self.stage(bypass_type_check=bypass_type_check, **kwargs)
        if not self.emit_when_ready: # avoid redundant emit
            self.emit()

    def pack_payload(self):
        """
        Called to pack the payload - 
        Only after all of the required items have been staged
        """
        if self.pack_payload_callback:
            staged_dict = {
                name: item['value'] 
                for name, item in self.required_items.items()
                }
            return self.pack_payload_callback(**staged_dict)
        else:
            raise ValueError(f"pack_payload_callback must be set for port '{self.name}'")

    def __gt__(self, other):
        """Implements self.connect(other) through el1.some_output > el2.some_input"""
        self.connect(other)

    def _emit_ready_check(self):
        return all(item['value'] is not None for item in self.required_items.values())

    @param.depends('emit_ready', watch=True)
    def _emit_ready_watcher(self):
        """
        When the emit is ready, we can assume that the type-checks
        have been successful, and so, we set type_check_successful to True
        """
        if self._emit_ready_check():
            self.type_check_successful = True


class Ports(param.Parameterized):
    """Keeps track of InputPorts and OutputPorts and handles their creation"""
    input = param.Dict(default={}, doc="Dictionary to store input ports")
    output = param.Dict(default={}, doc="Dictionary to store output ports")

    def __init__(self, containing_element=None, **params):
        super().__init__(**params)
        self.containing_element = containing_element


    def add_input(self, name: str, unpack_payload_callback, **kwargs):
        input_port = InputPort(
            name=name,
            unpack_payload_callback=unpack_payload_callback,
            containing_element=self.containing_element,
            **kwargs)
        self.input[name] = input_port
        return input_port
    
    def add_output(self, name: str, pack_payload_callback, **kwargs):
        output_port = OutputPort(
            name=name,
            pack_payload_callback=pack_payload_callback,
            containing_element=self.containing_element,
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
        if isinstance(value, InputPort):
            self.input[name] = value
        elif isinstance(value, OutputPort):
            self.output[name] = value
        else:
            super().__setattr__(name, value)