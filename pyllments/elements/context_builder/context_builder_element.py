from dataclasses import dataclass, field
from typing import Callable, Optional

import param
import jinja2
from jinja2 import meta
import asyncio
import time

from pyllments.elements.flow_control import FlowController
from pyllments.payloads.message import MessagePayload
from pyllments.ports import InputPort, Ports
from pyllments.base.element_base import Element
from .to_message import to_message_payload, payload_message_mapping


@dataclass
class ContextItem:
    """
    Single source of truth for one entry in the ``input_map``.

    Replaces the previous set of parallel dicts (port_types, port_roles,
    constants, templates, ...) so that every helper reads one object instead
    of cross-referencing several dicts keyed by name.

    Attributes
    ----------
    name : str
        The item's key in ``input_map``.
    kind : str
        One of ``'port'``, ``'constant'``, or ``'template'``.
    role : str or None
        Role override. ``None`` on ports preserves the incoming message roles.
    persist : bool
        Ports only: keep the payload available across triggers when ``True``.
    depends_on : list of str
        Explicit dependencies; the item is only included when all are present.
    template_vars : list of str
        Templates only: variable names parsed from the template string.
    constant_payload : MessagePayload or None
        Constants only: the prebuilt message.
    template_str : str
        Templates only: the raw Jinja2 template.
    callback : callable or None
        Ports only: transforms the payload on arrival (may be async).
    message_fn : callable or None
        Optional per-item override for payload -> MessagePayload conversion.
    full_deps : frozenset of str
        Pre-computed set of regular ports whose payloads are required before
        this item can contribute to the output.
    satisfiable : bool
        ``False`` when the dependency chain is broken (undefined dep or cycle),
        meaning the item can never produce a message.
    """
    name: str
    kind: str
    role: Optional[str] = None
    persist: bool = False
    depends_on: list = field(default_factory=list)
    template_vars: list = field(default_factory=list)
    constant_payload: Optional[MessagePayload] = None
    template_str: str = ''
    callback: Optional[Callable] = None
    message_fn: Optional[Callable] = None
    full_deps: frozenset = frozenset()
    satisfiable: bool = True


class ContextBuilderElement(Element):
    """
    Aggregates messages from various sources (input ports, constants, templates)
    and emits them as a single, ordered list of MessagePayloads.

    Handles payload conversion, port persistence, optional items, and
    dependency checks so messages are emitted only when their conditions are
    met. Uses a sequential processing model; one trigger is built at a time.

    Role Assignment:
    - Ports without explicit 'role': preserve original message roles.
    - Ports with explicit 'role': override all messages with that role.
    - Constants/Templates: use the specified role or defaults ('user'/'system').

    Key Concepts:
    - Input Sources: Defined via `input_map`. Each entry is one of:
        - Port: receives payloads dynamically; may be marked `persist=True`.
        - Constant: fixed message (kind='constant' or name ends with '_constant').
        - Template: Jinja2 string rendered from port payloads (kind='template'
          or name ends with '_template'). Template variables implicitly create
          dependencies on the ports they name.
      The entry kind is taken from an explicit `'kind'` key when present, and
      otherwise inferred from the name suffix.
    - Emission Control: `trigger_map`, `emit_order`, or `build_fn` determine the
      sequence of items to include in the output list.
    - Optional Items: items in `trigger_map`/`emit_order` wrapped in square
      brackets (e.g. `[history]`) are included when available but never block
      emission.
    - Dependencies:
        - Trigger/Order: all non-optional items in the active order must have
          their dependency chains satisfied for emission to occur.
        - Explicit (`depends_on`): any item may declare `depends_on`; it is only
          included when those ports have payloads.
        - Template Variables: templates implicitly depend on the ports named in
          the template (e.g. `{{ user_msg }}`).

    Example:
    ```python
    context_builder = ContextBuilderElement(
        input_map={
            'system_prompt_constant': {'role': 'system', 'message': "You are helpful."},
            'history': {
                'payload_type': list[MessagePayload],
                'ports': [history_handler.ports.output['history_output']],
                'persist': True
            },
            'history_header_constant': {
                'role': 'system', 'message': "Chat History:", 'depends_on': 'history'
            },
            'user_query': {
                'role': 'user', 'ports': [chat_ui.ports.output['message_output']]
            }
        },
        trigger_map={
            'user_query': [
                'system_prompt_constant',
                '[history_header_constant]',
                '[history]',
                'user_query'
            ]
        }
    )
    ```
    """
    # ---- Configuration Parameters ----

    input_map = param.Dict(default={}, doc="""
        Maps a port/constant/template name to its configuration dict.
        - Common (optional): 'kind' ('port' | 'constant' | 'template') to set the
          entry type explicitly instead of relying on the name suffix.
          'depends_on' (str or list) to gate inclusion on other items.
          'message_fn' (callable) to override payload -> MessagePayload conversion
          for this item; it receives the payload and returns a MessagePayload
          (or list of them).
        - Ports: 'payload_type' and/or 'ports', optional 'role', 'persist'
          (default False), and 'callback' (may be async) to transform the
          payload on arrival.
        - Constants (name ends with '_constant' or kind='constant'): 'role' and
          'message'.
        - Templates (name ends with '_template' or kind='template'): 'role' and
          'template' (Jinja2). Define templates after the ports they reference.

        Example:
        input_map = {
            'port_a': {'role': 'user', 'persist': True, 'ports': [el1.ports.output['some_output']]},
            'port_b': {'role': 'assistant', 'payload_type': list[MessagePayload]},
            'user_constant': {'role': 'user', 'message': "This text will be a user message"},
            'system_template': {'role': 'system', 'template': "{{ port_a }}  --  {{ port_b }}"},
            'history_header_constant': {'role': 'system', 'message': "Chat history:", 'depends_on': 'history'}
        }
        """)

    emit_order = param.List(default=[], doc="""
        Item names in emission order. Used when neither trigger_map nor build_fn
        is provided. Waits until all required payloads are available.
        Mark optional items with square brackets: ['required_item', '[optional_item]'].
        """)

    trigger_map = param.Dict(default={}, doc="""
        Maps a trigger port name to the ordered list of items to build when that
        port receives a payload.
        Mark optional items with square brackets.

        Example:
        trigger_map = {
            'query': ['system_msg_constant', '[history]', 'query'],
            'tool_response': ['system_msg_constant', 'query', 'tool_response']
        }
        """)

    build_fn = param.Callable(default=None, doc="""
        Advanced alternative to trigger_map: a function returning the ordered
        list of item names to emit. Receives the flow kwargs (active_input_port,
        c, and the flow ports).""")

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")

    outgoing_input_ports = param.List(default=[], item_type=InputPort, doc="""
        Input ports to connect to the flow controller's messages_output port.""")

    payload_message_mapping = param.Dict(default=payload_message_mapping, doc="""
        Mapping between payload types and message conversion functions.""")

    ports = param.ClassSelector(class_=Ports, doc="""
        The ports object for the context builder.""")

    _is_processing = param.Boolean(False, precedence=-1, doc="""
        Internal flag indicating a trigger flow is currently being built.""")

    # ---- Initialization ----

    def __init__(self, **params):
        self.items = {}              # name -> ContextItem (single source of truth)
        self.required_ports = []     # port names, for progress logging only
        self._pending_trigger = None
        self._is_processing = False

        self._build_items(params['input_map'])

        super().__init__(**params)

        self._setup_flow_controller()

        if self.outgoing_input_ports:
            for port in self.outgoing_input_ports:
                self.ports.messages_output > port

        self._precompute_dependencies()
        self._validate_configuration()

    # ---- Input Map -> ContextItem ----

    def _infer_kind(self, name):
        """Infer item kind from the name suffix when not stated explicitly."""
        if name.endswith('_constant'):
            return 'constant'
        if name.endswith('_template'):
            return 'template'
        return 'port'

    def _build_items(self, input_map):
        """Turn the input_map into ContextItem instances."""
        if not input_map:
            return
        for name, config in input_map.items():
            if not isinstance(config, dict) or name == 'output':
                continue
            self.items[name] = self._make_item(name, config)
            if self.items[name].kind == 'port' and name != 'messages_output':
                self.required_ports.append(name)

    def _make_item(self, name, config):
        """Construct a ContextItem from a single input_map entry."""
        kind = config.get('kind') or self._infer_kind(name)

        depends_on = config.get('depends_on', [])
        if isinstance(depends_on, str):
            depends_on = [depends_on]

        item = ContextItem(
            name=name,
            kind=kind,
            depends_on=list(depends_on),
            message_fn=config.get('message_fn'),
        )

        if kind == 'constant':
            item.role = config.get('role', 'user')
            item.constant_payload = MessagePayload(content=config.get('message', ''), role=item.role)
        elif kind == 'template':
            item.role = config.get('role', 'system')
            item.template_str = config.get('template', '')
            parsed = jinja2.Environment().parse(item.template_str)
            item.template_vars = list(meta.find_undeclared_variables(parsed))
        else:  # port
            item.role = config.get('role')  # None preserves incoming roles
            item.persist = config.get('persist', False)
            item.callback = config.get('callback')

        return item

    # ---- Flow Controller Setup ----

    def _setup_flow_controller(self):
        """Set up the flow controller and adopt its ports as our own."""
        flow_map = self._create_flow_map()
        flow_fn = self._create_flow_function()
        self.flow_controller = FlowController(
            containing_element=self,
            flow_map=flow_map,
            flow_fn=flow_fn,
        )
        self.ports = self.flow_controller.ports

    def _create_flow_map(self):
        """Create the flow map for the flow controller (port items only)."""
        flow_map = {
            'input': {},
            'output': {'messages_output': {"payload_type": list[MessagePayload]}},
        }
        for name, config in self.input_map.items():
            item = self.items.get(name)
            if not item or item.kind != 'port':
                continue
            port_config = config.copy()
            if ('payload_type' not in port_config) and ('ports' not in port_config):
                raise ValueError(f"Payload type or ports not specified for port {name}")
            # Force persistence on every flow port so payloads that arrive before
            # their trigger remain available while a context is assembled. We then
            # clear the genuinely non-persistent ports ourselves after emission
            # (see _clear_consumed_ports); the FlowController's own per-port
            # clearing only covers the active port, not the others we consume.
            port_config['persist'] = True
            flow_map['input'][name] = port_config
        return flow_map

    def _create_flow_function(self):
        """Create the async flow function driving emission."""
        async def flow_fn(**kwargs):
            active_port = kwargs['active_input_port']
            messages_output = kwargs['messages_output']
            active_name = active_port.name

            self._log_progress(active_name)
            await self._apply_callback(active_name, active_port)

            if not self._acquire_trigger(active_name):
                return None

            order = self._get_message_order(kwargs, self._pending_trigger)

            start_time = time.perf_counter()
            emitted = await self._process_messages(messages_output, order)
            self.logger.debug(
                "ContextBuilderElement: building trigger '{}' took {:.4f}s",
                self._pending_trigger,
                time.perf_counter() - start_time,
            )

            if emitted:
                self._clear_consumed_ports(order)
                self.logger.debug("Emitted; releasing lock for trigger {}", self._pending_trigger)
                self._release_processing_lock()
            elif self._order_unsatisfiable(order):
                # Misconfigured order (undefined item or broken dependency chain):
                # release rather than wedge the lock forever.
                self.logger.debug("Releasing lock for trigger {}: order cannot be satisfied", self._pending_trigger)
                self._release_processing_lock()
            return None
        return flow_fn

    def _log_progress(self, active_name):
        """Emit a debug line summarising how many required ports are ready."""
        ready = [
            name for name in self.required_ports
            if getattr(self.flow_controller.flow_port_map.get(name), 'payload', None) is not None
        ]
        missing = [name for name in self.required_ports if name not in ready]
        self.logger.debug(
            "Received payload on '{}'. Progress: {}/{} ready; Missing: {}",
            active_name, len(ready), len(self.required_ports), missing,
        )

    async def _apply_callback(self, active_name, active_port):
        """Run a port's arrival callback, awaiting async results."""
        item = self.items.get(active_name)
        if not item or item.callback is None or active_port.payload is None:
            return
        result = item.callback(active_port.payload)
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Task):
            active_port.payload = await result
        else:
            active_port.payload = result

    def _acquire_trigger(self, active_name):
        """
        Decide whether this arrival should drive emission.

        Returns True when there is a pending trigger to process. A new trigger is
        started only for a triggerable port; while one is pending, any later
        arrival (e.g. a dependency the trigger was waiting on) feeds that same
        pending trigger so it can complete once its dependencies are present.
        """
        if self._is_processing:
            self.logger.debug("Received {} while building trigger {}", active_name, self._pending_trigger)
            return True

        if not self._is_triggerable(active_name):
            self.logger.trace("Ignoring non-trigger port {}", active_name)
            return False

        self._is_processing = True
        self._pending_trigger = active_name
        self.logger.debug("Acquired lock for trigger {}", active_name)
        return True

    def _is_triggerable(self, active_name):
        """Whether an arrival on this port can start a new trigger flow."""
        if self.build_fn:
            return True
        if self.trigger_map:
            return active_name in self.trigger_map
        if self.emit_order:
            return active_name in [self._get_real_name(n) for n in self.emit_order]
        return False

    def _release_processing_lock(self):
        """Reset sequential trigger state so a new trigger can be processed."""
        self._is_processing = False
        self._pending_trigger = None

    def _clear_consumed_ports(self, order):
        """Clear non-persistent port payloads that were just emitted."""
        for spec in order:
            item = self.items.get(self._get_real_name(spec))
            if item and item.kind == 'port' and not item.persist:
                self.flow_controller.flow_port_map[item.name].payload = None

    # ---- Optional Item Helpers ----

    def _is_optional(self, name):
        """Whether a name is wrapped in square brackets (optional)."""
        return name.startswith('[') and name.endswith(']')

    def _get_real_name(self, name):
        """Strip optional brackets to get the underlying item name."""
        return name[1:-1] if self._is_optional(name) else name

    # ---- Message Ordering & Assembly ----

    def _get_message_order(self, kwargs, trigger):
        """
        Resolve the emission order. Priority:
        1. build_fn  2. trigger_map[trigger]  3. emit_order  4. all items sorted.
        """
        if self.build_fn:
            return self.build_fn(**kwargs)
        if self.trigger_map and trigger in self.trigger_map:
            return self.trigger_map[trigger]
        if self.emit_order:
            return self.emit_order
        return sorted(self.items.keys())

    async def _process_messages(self, messages_output, order):
        """Build and emit the message list for a ready order. Returns True if emitted."""
        if not order or not self._order_ready(order):
            return False

        messages = []
        for spec in order:
            msg = self._get_message(spec)
            if msg:
                messages.extend(msg) if isinstance(msg, list) else messages.append(msg)
            elif not self._is_optional(spec):
                self.logger.warning("Required item '{}' produced no message", spec)

        if messages:
            await messages_output.emit(messages)
            return True
        return False

    # ---- Readiness Checks ----

    def _order_unsatisfiable(self, order):
        """True when a non-optional order item can never succeed (bad config)."""
        if not order:
            return True
        for spec in order:
            if self._is_optional(spec):
                continue
            item = self.items.get(self._get_real_name(spec))
            if item is None or not item.satisfiable:
                return True
        return False

    def _order_ready(self, order):
        """True when every non-optional item's required ports have payloads."""
        if self._order_unsatisfiable(order):
            return False
        needed = set()
        for spec in order:
            if self._is_optional(spec):
                continue
            needed |= self.items[self._get_real_name(spec)].full_deps
        return self._ports_have_payloads(needed)

    def _ports_have_payloads(self, port_names):
        """True when all named flow ports currently hold a payload."""
        for name in port_names:
            flow_port = self.flow_controller.flow_port_map.get(name)
            if not flow_port or flow_port.payload is None:
                return False
        return True

    def _dependency_met(self, name):
        """True when a depends_on target exists and (if a port) has a payload."""
        item = self.items.get(name)
        if item is None:
            return False
        if item.kind == 'port':
            flow_port = self.flow_controller.flow_port_map.get(name)
            return bool(flow_port and flow_port.payload is not None)
        return True

    # ---- Message Retrieval & Conversion ----

    def _get_message(self, spec):
        """
        Produce the message(s) for an order item. Returns None when the item is
        unavailable (which is fine for optional items). Assumes order-level
        readiness has already been checked by _order_ready.
        """
        real_name = self._get_real_name(spec)
        item = self.items.get(real_name)
        if item is None:
            self.logger.warning("Item '{}' requested in order but not defined.", real_name)
            return None

        # An item is skipped if any of its non-optional depends_on are unmet,
        # even when the item itself is optional in the order.
        for dep_spec in item.depends_on:
            if not self._is_optional(dep_spec) and not self._dependency_met(self._get_real_name(dep_spec)):
                self.logger.debug("Item '{}' skipped: dependency '{}' not met.", real_name, dep_spec)
                return None

        if item.kind == 'constant':
            return item.constant_payload
        if item.kind == 'template':
            return self._render_template(item)

        flow_port = self.flow_controller.flow_port_map.get(real_name)
        if flow_port and flow_port.payload is not None:
            return self._convert_payload_to_message(real_name, flow_port.payload, item.role, item.message_fn)
        return None

    def _render_template(self, item):
        """Render a template item against its dependency port payloads."""
        context = {}
        for var_spec in item.template_vars:
            real_var = self._get_real_name(var_spec)
            flow_port = self.flow_controller.flow_port_map.get(real_var)
            payload = flow_port.payload if flow_port else None
            if payload is None:
                self.logger.error(
                    "Template '{}' missing payload for required variable '{}'.",
                    item.name, real_var,
                )
                return None
            dep_item = self.items.get(real_var)
            msg = self._convert_payload_to_message(
                real_var, payload,
                dep_item.role if dep_item else None,
                dep_item.message_fn if dep_item else None,
            )
            if msg is None:
                self.logger.error(
                    "Failed to convert payload for template variable '{}' in '{}'.",
                    real_var, item.name,
                )
                return None
            context[real_var] = msg.model.content if hasattr(msg, 'model') else str(msg)

        try:
            env = jinja2.Environment(undefined=jinja2.StrictUndefined)
            rendered = env.from_string(item.template_str).render(**context)
            return MessagePayload(content=rendered, role=item.role)
        except jinja2.exceptions.UndefinedError as e:
            self.logger.debug("Template '{}' skipped (missing variable): {}", item.name, e)
            return None
        except Exception as e:
            self.logger.error("Error rendering template '{}': {}", item.name, e, exc_info=True)
            return None

    def _convert_payload_to_message(self, name, payload, role=None, message_fn=None):
        """
        Convert a payload into a MessagePayload (or list of them).

        Uses an item-specific `message_fn` when provided, otherwise the
        `payload_message_mapping`. Mixed-type lists (e.g. HistoryHandler
        context_output) are converted per item.
        """
        if payload is None:
            return None

        if message_fn is None:
            item = self.items.get(name)
            if item is not None:
                message_fn = item.message_fn
        if message_fn is not None:
            return message_fn(payload)

        if isinstance(payload, list) and payload:
            item_types = {type(item) for item in payload}
            if len(item_types) > 1:
                messages = []
                for element in payload:
                    convert_kwargs = {
                        "payload": element,
                        "payload_message_mapping": self.payload_message_mapping,
                        "expected_type": type(element),
                    }
                    if role is not None:
                        convert_kwargs["role"] = role
                    converted = to_message_payload(**convert_kwargs)
                    messages.extend(converted) if isinstance(converted, list) else messages.append(converted)
                return messages

        if name in self.flow_controller.flow_port_map:
            expected_type = self.flow_controller.flow_port_map[name].payload_type
        else:
            expected_type = type(payload)

        return to_message_payload(
            payload,
            self.payload_message_mapping,
            expected_type=expected_type,
            role=role,
        )

    # ---- Dependency Pre-computation & Validation ----

    def _precompute_dependencies(self):
        """Compute each item's full required-port set and satisfiability."""
        self._dep_computed = set()
        for name in self.items:
            self._resolve_deps(name, set())

    def _resolve_deps(self, name, visiting):
        """
        Recursively resolve the set of regular ports an item needs.

        Returns the frozenset of required port names, or None when the item is
        undefined or its non-optional dependency chain is broken (incl. cycles).
        Results are cached on the ContextItem (full_deps + satisfiable).
        """
        real_name = self._get_real_name(name)
        item = self.items.get(real_name)
        if item is None:
            return None  # undefined reference
        if real_name in self._dep_computed:
            return item.full_deps if item.satisfiable else None
        if real_name in visiting:
            self.logger.warning("Dependency cycle detected involving '{}'.", real_name)
            return None

        visiting.add(real_name)
        deps = set()
        satisfiable = True
        if item.kind == 'port':
            deps.add(real_name)

        specs = list(item.depends_on)
        if item.kind == 'template':
            specs += item.template_vars

        for spec in specs:
            if self._is_optional(spec):
                continue
            sub = self._resolve_deps(spec, visiting)
            if sub is None:
                satisfiable = False
                break
            deps |= sub

        visiting.discard(real_name)
        item.satisfiable = satisfiable
        item.full_deps = frozenset(deps) if satisfiable else frozenset()
        self._dep_computed.add(real_name)
        return item.full_deps if satisfiable else None

    def _validate_configuration(self):
        """
        Warn (do not raise) about references that can never resolve.

        Undefined references degrade to "no emission" at runtime by design, so
        this surfaces likely mistakes in logs without breaking that contract.
        """
        referenced = set()
        for order in [self.emit_order, *self.trigger_map.values()]:
            for spec in order:
                referenced.add(self._get_real_name(spec))
        for name in referenced:
            if name not in self.items:
                self.logger.warning("Order references undefined item '{}'; it will be skipped.", name)

        for name, item in self.items.items():
            for dep_spec in item.depends_on:
                real_dep = self._get_real_name(dep_spec)
                if real_dep not in self.items:
                    self.logger.warning("Item '{}' depends_on undefined item '{}'.", name, real_dep)
            if item.kind == 'template':
                for var_spec in item.template_vars:
                    if self._get_real_name(var_spec) not in self.items:
                        self.logger.warning("Template '{}' uses undefined variable '{}'.", name, var_spec)
            if not item.satisfiable:
                self.logger.warning("Item '{}' has an unsatisfiable dependency chain; it will never emit.", name)
