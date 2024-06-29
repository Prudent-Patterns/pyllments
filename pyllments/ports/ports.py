from typing import TYPE_CHECKING, Union, List
import inspect
import warnings

import param

from pyllments.base.payload_base import Payload


class Port(param.Parameterized):
    """Base implementation of Port - InputPort and OutputPort inherit from this"""

    payload = param.ClassSelector(class_=Payload)
    containing_element = param.Parameter(default=None, precedence=-1)
    connected_elements = param.List()

    def __init__(self, **params):
        super().__init__(**params)
        # Set as attribute and clear parameter to avoid circular param __repl__
        self._containing_element = self.containing_element
        self.containing_element = None


class InputPort(Port):
    subject_ports = param.List(item_type=Port)

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
    # Add a watcher IF updating of required_items becomes necessary
    required_items = param.List(item_type=Union[str, tuple[str, type]], doc="""
        Type checking automatically enabled if (name, type) tuple is passed""")

    emit_when_ready = param.Boolean(default=True, doc="""
        If true, the payload will be emitted when the required items are staged""")

    emit_ready = param.Boolean(default=False, doc="""
        True when the required items have been staged and the payload can be emitted""")

    infer_from_callback = param.Boolean(default=True, doc="""
        If true, infers the required items from pack_payload_callback
        and required_items is set to None""")

    observer_ports = param.List(item_type=Port, doc="""
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
            if (self.infer_from_callback and
                not inspect.getfullargspec(self.pack_payload_callback).annotations):

                raise ValueError("""
                    pack_payload_callback must have annotations if infer_from_callback
                    is False""")
            if self.payload is not None:
                warnings.warn("""payload will be overridden with the return type of 
                    pack_payload_callback""")
            self.type_checking = True
            annotations = inspect.getfullargspec(self.pack_payload_callback).annotations
            self.param.payload.class_ = annotations.pop('return')
            self.required_items =  tuple(annotations.items())
        # In the case of desired type-checking
        elif self.required_items and (isinstance(self.required_items[0], tuple)):
            self.type_checking = True
            for item in self.required_items:
                self.param.add_parameter(
                    item[0],
                    param.ClassSelector(class_=[item[1]])
                    )
        # In case of no type-checking but required_items specified
        elif str and (not self.required_items):
            for item in self.required_items:
                self.param.add_parameter(item, param.Parameter())
        elif not self.required_items:
            self.type_checking = False

    def connect(self, other: InputPort):
        """Connects self and the other InputPort"""
        if not isinstance(other, InputPort):
            raise ValueError('Can only connect OutputPorts to InputPorts')
        if not isinstance(other.payload, type(self.payload)):
            raise ValueError('InputPort and OutputPort payload types must match')
        
        self.observer_ports.append(other)
        self.connected_elements.append(other._containing_element)
        other.connected_elements.append(self._containing_element)
    
    def stage(self, **kwargs: param.Parameter):
        """Stages the values within the port before packing"""
        if self.type_checking:
            for name, value in kwargs.items():
                class_ = self.param[name].class_
                if isinstance(value, class_):
                    self.staged_items.append(name)
                    self.param[name] = value
            # Compare equality of staged_items and required_items
            if set(self.staged_items) == set(item[0] for item in self.required_items):
                self.emit_ready = True
        else:
            for name, value in kwargs.items():
                self.staged_items.append(name)
                self.param[name] = value
            if set(self.staged_items) == set(item[0] for item in self.required_items):
                self.emit_ready = True
        if self.emit_when_ready and self.emit_ready:
            self.emit()

    def emit(self):
        """Packs the payload and emits it to all registered observers"""
        if not self.emit_ready:
            raise Exception('Staged items do not match required items')
        else:
            self.payload = self.pack_payload()
        for port in self.observer_ports:
            port.receive(self.payload)
        # For returning the payload to the caller 
        return self.payload
    
    def stage_and_emit(self, **kwargs):
        """Stages the payload and emits it - All required params need be present"""
        self.stage(**kwargs)
        self.emit()

    def pack_payload(self):
        if self.pack_payload_callback:
            staged_dict = {}
            for item in self.staged_items:
                staged_dict[item] = getattr(self, item)
            return self.pack_payload_callback(**staged_dict)
        else:
            raise ValueError('pack_payload_callback must be set')
            #TODO Implement default callback based on the payload type

    def __gt__(self, other):
        """Implements self.connect(other) through el1.some_input > el2.some_output"""
        self.connect(other)
        


class InputPorts(param.Parameterized):
    containing_element = param.Parameter(precedence=-1)

    def __init__(self, **params):
        self._containing_element = self.containing_element
        self.containing_element = None

    def add(self, name, payload_type, **kwargs): 
        input_port = InputPort(
            payload=payload_type(), # Overridden if pack_payload_callback is passed
            **kwargs
            )

        self.param.add_parameter(name, param.Parameter(input_port))
        return input_port

class OutputPorts(param.Parameterized):
    containing_element = param.Parameter(precedence=-1)

    def __init__(self, **params):
        self._containing_element = self.containing_element
        self.containing_element = None

    def add(self, name, payload_type=None, **kwargs):
        if payload_type:
            if kwargs.get('payload'):
                warnings.warn(
                    "payload_type will override the payload argument if both are provided." 
                )
            kwargs['payload'] = payload_type()
        output_port = OutputPort(**kwargs)
        self.param.add_parameter(name, param.Parameter(output_port))
        return output_port

class Ports(param.Parameterized):
    """Keeps track of InputPorts and OutputPorts and handles their creation"""
    input = param.ClassSelector(class_=InputPorts, default=InputPorts())
    output = param.ClassSelector(class_=OutputPorts, default=OutputPorts())
    containing_element = param.Parameter(precedence=-1)

    def __init__(self, **params):
        super().__init__(**params)
        self._containing_element = self.containing_element
        self.containing_element = None

    def add_input(self, **kwargs): 
        self.input.add(
            containing_element=self._containing_element,
            **kwargs
            )
    
    def add_output(self, **kwargs):
        self.output.add(
            containing_element=self._containing_element,
            **kwargs
            )
