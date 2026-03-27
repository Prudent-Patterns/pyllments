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

## Runtime expectations

- Assume config injection is handled by recipe execution machinery.
- Avoid hand-rolled config bootstrap code unless required by framework changes.
- Keep defaults sensible while supporting CLI overrides.

## Authoring checklist

- [ ] Recipe uses a `Config` dataclass for runtime options.
- [ ] Element graph wiring is explicit and readable.
- [ ] User-facing run path is compatible with `pyllments recipe run ...`.
- [ ] Example/default config behavior is documented in code comments or docs.

## Reference

- `pyllments/recipes/chat/chat.py`
