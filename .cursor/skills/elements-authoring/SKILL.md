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

## Reactivity and views

- Use `self.watch(...)` for view watchers so lifecycle cleanup remains safe.
- Keep view creation in `@Component.view`-decorated methods.
- Treat view code as presentation and interaction glue, not business logic.

## Authoring checklist

- [ ] Element subclasses the project Element base class.
- [ ] Model is set on `self.model` and receives relevant params.
- [ ] Ports are explicitly created and wired in a predictable order.
- [ ] Reactive handlers call model methods with minimal side effects.
- [ ] View state and model state stay synchronized.

## References

- `pyllments/base/element_base.py`
- `pyllments/base/component_base.py`
- `pyllments/elements/chat_interface/chat_interface_element.py`
- `pyllments/recipes/chat/chat.py`
