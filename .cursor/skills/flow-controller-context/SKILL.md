---
name: flow-controller-context
description: Applies project context and guardrails when working with the FlowController class. Use when modifying FlowController behavior, orchestration logic, or related control-flow APIs.
---

# FlowController Context

## Baseline expectations

- Keep control-flow APIs explicit and easy to reason about.
- Prefer small, composable methods over monolithic branching logic.
- Preserve existing behavior unless a change is intentional and tested.

## Safety checklist

- [ ] Control transitions are deterministic.
- [ ] Error paths are explicit and observable.
- [ ] Public API changes are documented and test-covered.
- [ ] Integration points with Elements/Ports remain compatible.
