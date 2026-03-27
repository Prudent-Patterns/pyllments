---
name: ports-connectivity
description: Designs and updates Pyllments port wiring and payload flow contracts. Use when editing pyllments/ports/ports.py, element port definitions, or when discussing input/output port behavior and emission rules.
---

# Ports Connectivity

## Port intent

- Input ports receive payloads and trigger element-internal behavior.
- Output ports emit payloads to connected input ports.
- Preserve observer semantics: outputs notify connected inputs.

## Naming convention

- Use `*_input` for inputs that do not directly trigger output emission.
- Use `*_emit_input` for inputs that do trigger output emission.
- Keep names explicit about intent and payload type.

## Wiring and order

- Build ports in deterministic setup functions called from `__init__`.
- Be careful with connection order because connecting can trigger events.
- Validate payload compatibility between connected ports before wiring.

## Authoring checklist

- [ ] Input/output payload expectations are explicit.
- [ ] Port names match behavior (`*_input` vs `*_emit_input`).
- [ ] Connection side effects are intentional and test-covered.
- [ ] Emission paths avoid accidental loops or duplicate sends.

## Reference

- `pyllments/ports/ports.py`
