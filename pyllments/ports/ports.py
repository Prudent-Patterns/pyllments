from typing import TYPE_CHECKING, Union, List, Dict
import inspect
import warnings

import param

from pyllments.base.payload_base import Payload


class Port(param.Parameterized):
    """Base implementation of Port - InputPort and OutputPort inherit from this"""

    payload = param.ClassSelector(class_=Payload, allow_None=True)
    containing_element = param.Parameter(default=None, precedence=-1)
    connected_elements = param.List()

    def __init__(self, **params):
        super().__init__(**params)
        # Set as attribute and clear parameter to avoid circular param __repl__
        self._containing_element = self.containing_element
        self.containing_element = None


class InputPort(Port):
    output_ports = param.List(item_type=Port)

    unpack_payload_callback = param.Callable(doc="""
        The callback used to unpack the payload - has payload as its only argument.
        Unpacks the payload and connects it to the element's model""")

    def receive(self, payload):
        self.payload = payload
        if not self.unpack_payload_callback:
            raise ValueError('unpack_payload_callback must be set')
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
        If true, type-checking is enabled""")

    def __init__(self, **params: param.Parameter):
        super().__init__(**params)

        # In the case when pack_payload_callback is passed and so is infer_from_callback
        if self.pack_payload_callback and self.infer_from_callback:
            annotations = inspect.getfullargspec(self.pack_payload_callback).annotations
            if (self.infer_from_callback and not annotations):
                raise ValueError("""
                    pack_payload_callback must have annotations if infer_from_callback
                    is False""")
            if self.payload is not None:
                warnings.warn("""payload will be overridden with the return type of 
                    pack_payload_callback""")
            self.type_checking = True
            self.param.payload.class_ = annotations.pop('return')
            self.required_items = {
                name: {'value': None, 'type': type_}
                for name, type_ in annotations.items()
                }
        # In the case of desired type-checking - enabled when required items are tuples
        elif self.required_items and next(iter(self.required_items))['type']:
            self.type_checking = True
        # No type checking, just a list of required items
        elif self.required_items:
            self.required_items = {item: {'value': None, 'type': None} for item in self.required_items}

    def connect(self, other: InputPort):
        """Connects self and the other InputPort"""
        if not isinstance(other, InputPort):
            raise ValueError('Can only connect OutputPorts to InputPorts')
        if not isinstance(other.payload, type(self.payload)):
            raise ValueError('InputPort and OutputPort payload types must match')
        
        self.input_ports.append(other)
        self.connected_elements.append(other._containing_element)
        other.connected_elements.append(self._containing_element)
        other.output_ports.append(self)
    
    def stage(self, **kwargs: param.Parameter):
        """Stages the values within the port before packing"""
        for name, value in kwargs.items():
            if name not in self.required_items:
                raise ValueError(f'{name} is not a required item in {self.required_items}')
            if self.type_checking:
                expected_type = self.required_items[name]['type']
                if not isinstance(value, expected_type):
                    raise ValueError(f'{value} is not an instance of {expected_type}')
            self.required_items[name]['value'] = value
            self.staged_items.append(name)
        
        if self._emit_ready_check():
            self.emit_ready = True
        
        if self.emit_when_ready and self.emit_ready:
            self.emit()

    def emit(self):
        """Packs the payload and emits it to all registered observers"""
        if not self.emit_ready:
            raise Exception('Staged items do not match required items')
        else:
            self.payload = self.pack_payload()
        for port in self.input_ports:
            port.receive(self.payload)
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
            raise ValueError('pack_payload_callback must be set')
            #TODO Implement default callback based on the payload type

    def __gt__(self, other):
        """Implements self.connect(other) through el1.some_output > el2.some_input"""
        self.connect(other)

    def _emit_ready_check(self):
        return all(item['value'] is not None for item in self.required_items.values())


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
        input_port = InputPort(containing_element=self._containing_element, **kwargs)
        self.input[name] = input_port
        return input_port
    
    def add_output(self, name, **kwargs):
        output_port = OutputPort(containing_element=self._containing_element, **kwargs)
        self.output[name] = output_port
        return output_port
