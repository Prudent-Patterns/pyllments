---
name: model-authoring
description: Implements or refactors Pyllments models using param-based state and element-facing methods. Use when working on element models or when discussing where business logic should live.
---

# Model Authoring

## Model responsibilities

- Keep business logic and state transitions in the model.
- Expose callable methods that Elements invoke from port handlers.
- Avoid embedding UI concerns or view assembly in model methods.

## Param usage

- Define user-facing and reactive state with `param` fields near class top.
- Use clear defaults and constraints that reflect expected usage.
- Keep parameter naming stable for external callers.

## Element-model contract

- Model params are declared on the Model and may be passed through Element construction.
- The Element forwards `**params` to the Model once in `__init__`; the Model is the single owner of that state.
- Do not mirror model params onto the Element unless they are genuinely element-owned.
- `Model.__init__` ignores kwargs that are not declared on the model, so broad forwarding from elements is safe.
- Keep methods composable (`do_something`) so Element wiring stays clean.
- Preserve predictable behavior for port-triggered calls.

## Authoring checklist

- [ ] Model inherits from project Model base class.
- [ ] Core state is represented with `param` parameters.
- [ ] Methods are side-effect-aware and easy to call from Elements.
- [ ] Element can orchestrate reactivity without duplicating model logic.

## References

- `pyllments/base/model_base.py`
- `pyllments/elements/chat_gateway/chat_gateway_model.py`
