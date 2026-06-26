---
name: elements-authoring
description: Implements or refactors Pyllments elements with correct element-model-view-port patterns. Use when creating or modifying files in pyllments/elements or when the user asks about element design, wiring, or reactivity.
---

# Elements Authoring

## Core pattern

- Treat an Element as orchestration: it wires ports, model calls, and optional views.
- Keep business/domain logic primarily in the model, not in UI callbacks.
- Initialize model and reactive wiring in `__init__` and helper methods.
- Prefer hidden setup helpers (for example `_setup_ports`) called from `__init__`.

## Boundary and readiness pattern

- Element graph wiring should be topology only: use ports to connect elements, but do not rely on connection-time async side effects for schema/state setup.
- Give each element explicit readiness rules:
  - Resource readiness: await model/client/store setup before processing inputs that need it.
  - Data readiness: persist required payloads/schema/state in element-controlled slots.
  - Trigger readiness: only emit when a trigger input arrives and required data is available.
- If a trigger arrives before dependencies are ready, store the pending trigger or payload and stand by instead of emitting incomplete output.
- For schema/state-producing elements, prefer latched outputs that keep the latest payload available and emit when state changes.
- Keep fire-and-forget behavior explicit and trackable; if an element schedules work, provide an element-local `drain()` or readiness method when tests or callers need determinism.

## Reactivity and views

- Use `self.watch(...)` for view watchers so lifecycle cleanup remains safe.
- Keep view creation in `@Component.view`-decorated methods.
- Treat view code as presentation and interaction glue, not business logic.

## Authoring checklist

- [ ] Element subclasses the project Element base class.
- [ ] Model is set on `self.model` and receives relevant params.
- [ ] Ports are explicitly created and wired in a predictable order.
- [ ] Input handlers distinguish resource readiness from data/trigger readiness.
- [ ] Missing required inputs cause standby/pending state, not sleeps, broad task polling, or partial output.
- [ ] Reactive handlers call model methods with minimal side effects.
- [ ] View state and model state stay synchronized.

## References

- `pyllments/base/element_base.py`
- `pyllments/base/component_base.py`
- `pyllments/elements/chat_interface/chat_interface_element.py`
- `pyllments/recipes/chat/chat.py`
