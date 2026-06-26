---
name: ports-connectivity
description: Designs and updates Pyllments port wiring and payload flow contracts. Use when editing pyllments/ports/ports.py, element port definitions, or when discussing input/output port behavior and emission rules.
---

# Ports Connectivity

## Port intent

- Input ports receive payloads and trigger element-internal behavior.
- Output ports emit payloads to connected input ports.
- Preserve observer semantics: outputs notify connected inputs.

## Runtime boundaries

- Treat `connect()` and `>` as graph construction only: ordered, synchronous, and side-effect-light.
- Do not hide async delivery or resource setup inside connection. Connection may validate types and update both sides of the edge, but it should not schedule background work.
- Treat `await stage_emit(...)` as the ordered delivery boundary: it should complete after connected input ports receive/process the payload and any returned downstream emit chain is awaited.
- Use explicit scheduling names (`schedule_task`, `schedule_stage_emit`) only when unordered/background work is intentional; pair scheduled work with a clear `drain()` or element-local cleanup point.

## Readiness model

- Resource readiness means external/model resources are usable; await checks such as `model.await_ready()` or port `readiness_check` before processing.
- Data readiness means required payloads/schema/state have arrived and are stored in element-controlled slots.
- Trigger readiness means an input event says "attempt output now"; the element may stand by if data readiness is not satisfied.
- Prefer element-local readiness gates over connection-time emits: an element can receive and store payloads while waiting for schema/state/resources, then emit when its readiness rules are satisfied.
- State/schema outputs should be latched when appropriate: keep the latest schema/state payload available so downstream logic does not depend on async connection side effects.

## Naming convention

- Use `*_input` for inputs that do not directly trigger output emission.
- Use `*_emit_input` for inputs that do trigger output emission.
- Keep names explicit about intent and payload type.

## Wiring and order

- Build ports in deterministic setup functions called from `__init__`.
- Preserve connection order because it determines delivery order for future emits.
- Validate payload compatibility between connected ports before wiring.
- If a connection appears to need an event, model that event as element readiness or a latched state/schema output rather than as hidden async work in `connect()`.

## Authoring checklist

- [ ] Input/output payload expectations are explicit.
- [ ] Port names match behavior (`*_input` vs `*_emit_input`).
- [ ] Connection only mutates graph topology; async side effects are modeled as readiness, emission, or explicit scheduled work.
- [ ] Required schema/state/resource readiness is represented by the receiving element, not by recipe-level sleeps or global activation.
- [ ] Emission paths avoid accidental loops or duplicate sends.

## Reference

- `pyllments/ports/ports.py`
