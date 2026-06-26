---
name: flow-controller-context
description: Applies project context and guardrails when working with the FlowController class. Use when modifying FlowController behavior, orchestration logic, or related control-flow APIs.
---

# FlowController Context

## Baseline expectations

- Keep control-flow APIs explicit and easy to reason about.
- Prefer small, composable methods over monolithic branching logic.
- Preserve existing behavior unless a change is intentional and tested.

## Readiness and emission

- FlowController-backed elements should treat incoming payloads as filling readiness slots, not necessarily as immediate output commands.
- Sync flow functions that need to emit must return the emit coroutine so `InputPort.receive()` can await it; async flow functions should directly `await` emits.
- Persist required inputs when a later trigger may need them, then clear only the ports actually consumed by a successful emission.
- If a trigger arrives before all required data is present, keep a pending trigger or return without emitting; do not sleep or schedule hidden background retries.
- Resource readiness belongs in awaited readiness checks (`model.await_ready`, port `readiness_check`) rather than connection callbacks.

## Safety checklist

- [ ] Control transitions are deterministic.
- [ ] Required data readiness is explicit and testable.
- [ ] Trigger handling does not emit partial output when required inputs are missing.
- [ ] Error paths are explicit and observable.
- [ ] Public API changes are documented and test-covered.
- [ ] Integration points with Elements/Ports remain compatible.
