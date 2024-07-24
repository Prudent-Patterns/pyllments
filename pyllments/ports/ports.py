from typing import TYPE_CHECKING, Union, List, Dict, get_origin, get_args
import inspect
import warnings

import param

from pyllments.common.param import PayloadSelector


class Port(param.Parameterized):
    """Base implementation of Port - InputPort and OutputPort inherit from this"""

    name = param.String(doc="The name of the port")
    payload = PayloadSelector(allow_None=True)
    containing_element = param.Parameter(default=None, precedence=-1)
    connected_elements = param.List()

    def __init__(self, name, **params):
        super().__init__(name=name, **params)
        # Set as attribute and clear parameter to avoid circular param __repl__
        self._containing_element = self.containing_element
        self.containing_element = None


class InputPort(Port):
    output_ports = param.List(item_type=Port)

    unpack_payload_callback = param.Callable(doc="""
        The callback used to unpack the payload - has payload as its only argument.
        Unpacks the payload and connects it to the element's model""")

    def __init__(self, **params):
        super().__init__(**params)
        if self.unpack_payload_callback:
            # Expects only one annotated argument
            annotations = inspect.getfullargspec(self.unpack_payload_callback).annotations
            first_arg_name = list(annotations.keys())[0] if annotations else None
            first_arg_annotation = annotations.get(first_arg_name, None)
            if first_arg_annotation is None:
                raise ValueError("The unpack_payload_callback must have an argument with an annotation.")
            
            # Set the payload type based on the first argument's annotation
            if get_origin(first_arg_annotation) is list:
                payload_type = List[get_args(first_arg_annotation)[0]]
            else:
                payload_type = first_arg_annotation
            
            self.param.payload.class_ = payload_type

    def receive(self, payload):
        self.payload = payload  # This will use the _validate method of PayloadSelector
        if not self.unpack_payload_callback:
            raise ValueError(f"unpack_payload_callback must be set for port '{self.name}'")
        self.unpack_payload_callback(payload)


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

    input_ports = param.List(item_type=Port, doc="""
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
            
            self.param.payload.class_ = return_annotation
            self.required_items = {
                name: {'value': None, 'type': type_}
                for name, type_ in annotations.items()
            }
            self.type_checking = True
        # In the case of desired type-checking - enabled when required items are tuples
        elif self.required_items and next(iter(self.required_items))['type']:
            self.type_checking = True
        # No type checking, just a list of required items
        elif self.required_items:
            self.required_items = {item: {'value': None, 'type': None} for item in self.required_items}

    def connect(self, other: InputPort):
        """Connects self and the other InputPort"""
        if not isinstance(other, InputPort):
            raise ValueError(f"Can only connect OutputPorts to InputPorts. "
                             f"Attempted to connect '{self.name}' ({type(self).__name__}) "
                             f"to '{other.name}' ({type(other).__name__})")
        
        # Check payload compatibility
        if not self._check_payload_compatibility(other):
            raise ValueError(f"""InputPort and OutputPort payload types are not compatible:
                OutputPort '{self.name}' in element '{self._containing_element.__class__.__name__}' 
                with payload type {self.param.payload.class_}
                InputPort '{other.name}' in element '{other._containing_element.__class__.__name__}' 
                with payload type {other.param.payload.class_}""")
        
        self.input_ports.append(other)
        self.connected_elements.append(other._containing_element)
        other.connected_elements.append(self._containing_element)
        other.output_ports.append(self)

    
    def _check_payload_compatibility(self, other: InputPort) -> bool:
        """Check if the payload types are compatible between self and other"""

        def is_compatible(output_type, input_type):
            # If types are identical, they're compatible
            if output_type == input_type:
                return True
            
            # Handle Union in input_type
            if get_origin(input_type) is Union:
                return any(is_compatible(output_type, t) for t in get_args(input_type))
            
            # Handle List types
            if get_origin(output_type) is List and get_origin(input_type) is List:
                return is_compatible(get_args(output_type)[0], get_args(input_type)[0])
            
            # Handle case where output is List but input accepts single or List
            if get_origin(output_type) is List:
                if get_origin(input_type) is List:
                    return is_compatible(get_args(output_type)[0], get_args(input_type)[0])
                else:
                    return is_compatible(get_args(output_type)[0], input_type)
            
            # Handle case where input is List but output is single
            if get_origin(input_type) is List:
                return is_compatible(output_type, get_args(input_type)[0])
            
            # Check for subclass relationship for Payload types
            return issubclass(output_type, input_type)

        output_type = self.param.payload.class_
        input_type = other.param.payload.class_

        if output_type is None or input_type is None:
            return False

        return is_compatible(output_type, input_type)

    def stage(self, **kwargs: param.Parameter):
        """Stages the values within the port before packing"""
        for name, value in kwargs.items():
            if name not in self.required_items:
                raise ValueError(f"'{name}' is not a required item for port '{self.name}'")
            if self.type_checking:
                expected_type = self.required_items[name]['type']
                if not isinstance(value, expected_type):
                    raise ValueError(f"For port '{self.name}', item '{name}' with value '{value}' "
                                     f"is not an instance of {expected_type}")
            self.required_items[name]['value'] = value
            self.staged_items.append(name)
        
        if self._emit_ready_check():
            self.emit_ready = True
        
        if self.emit_when_ready and self.emit_ready:
            self.emit()

    def emit(self):
        """Packs the payload and emits it to all registered observers"""
        if not self.emit_ready:
            raise Exception(f"Staged items do not match required items for port '{self.name}'")
        else:
            packed_payload = self.pack_payload()
            self.payload = packed_payload  # This will use the _validate method of PayloadSelector
        for port in self.input_ports:
            port.receive(self.payload)
        
        # Reset emit_ready and staged_items after emission
        self.emit_ready = False
        self.staged_items = []
        
        # Reset the values in required_items
        for item in self.required_items.values():
            item['value'] = None
        
        # For returning the payload to the caller 
        return self.payload
    
    def stage_emit(self, **kwargs):
        """Stages the payload and emits it - All required params need be present"""
        self.stage(**kwargs)
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
    containing_element = param.Parameter(precedence=-1)

    def __init__(self, **params):
        super().__init__(**params)
        self._containing_element = self.containing_element
        self.containing_element = None

    def add_input(self, name, **kwargs):
        input_port = InputPort(name=name, containing_element=self._containing_element, **kwargs)
        self.input[name] = input_port
        return input_port
    
    def add_output(self, name, **kwargs):
        output_port = OutputPort(name=name, containing_element=self._containing_element, **kwargs)
        self.output[name] = output_port
        return output_port