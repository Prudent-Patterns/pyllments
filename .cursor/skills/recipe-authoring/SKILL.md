---
name: recipe-authoring
description: Creates and updates runnable Pyllments recipes with config-driven entrypoints and element wiring. Use when editing files under recipes or when implementing CLI-runnable recipe flows.
---

# Recipe Authoring

## Recipe intent

- A recipe is a prebuilt app flow meant to run directly by users.
- Recipes should be parameterized through a `Config` dataclass.
- CLI options map into `Config`, then drive recipe behavior.

## Structure

- Place recipe modules under the `recipes` tree.
- Keep recipe setup focused on composing elements and wiring ports.
- Keep configuration parsing and flow assembly cleanly separated.

## Flow composition boundaries

- Recipe wiring should be topology-first: connect elements with `>`/`connect()` in readable order and let elements enforce their own readiness.
- Do not use sleeps or manual background-task polling to wait for schemas, tools, history, or other dependencies. Those should be modeled as element data readiness.
- Recipes can freely branch, fan out, clone subgraphs, and attach callbacks; the receiving element should decide whether a trigger is ready to emit.
- If a recipe introduces a resource-owning element, rely on that element's readiness/lifecycle methods rather than connection-time side effects.

## Runtime expectations

- Assume config injection is handled by recipe execution machinery.
- Avoid hand-rolled config bootstrap code unless required by framework changes.
- Keep defaults sensible while supporting CLI overrides.

## Authoring checklist

- [ ] Recipe uses a `Config` dataclass for runtime options.
- [ ] Element graph wiring is explicit and readable.
- [ ] Required schema/state/resource dependencies are handled by element readiness, not recipe-level sleeps.
- [ ] User-facing run path is compatible with `pyllments recipe run ...`.
- [ ] Example/default config behavior is documented in code comments or docs.

## Reference

- `pyllments/recipes/chat/chat.py`
