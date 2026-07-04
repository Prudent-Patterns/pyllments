---
name: docs-elements-authoring
description: Writes and updates Pyllments element documentation in Quarto using project conventions. Use when editing docs/elements/*.qmd or generating docs from element/model source files.
---

# Element Docs Authoring

## Scope

- Focus on documentation under `docs/elements/*.qmd`.
- Derive API and behavior details from element and model source.
- Keep argument and view notation consistent with existing docs style.

## Content expectations

- Document constructor parameters with clear defaults and intent.
- Include explicit element constructor args and forwarded model params (params declared on the model but accepted through element construction).
- Treat every public named element constructor argument as an Element `param`; flag code/docs drift if one is accepted but missing from `SomeElement.param`.
- Explain key views and interaction paths where relevant.
- Reflect real behavior from code; avoid speculative docs.

## Constructor documentation

- List element-owned args first (explicit constructor parameters declared on the Element).
- List model params users may pass through the element constructor (derive from the model's `param` declarations).
- Note when an element uses local filtering for multiple backends or special wiring.

## Authoring checklist

- [ ] Docs match current element/model signatures.
- [ ] Argument notation and formatting follow existing element docs.
- [ ] View-related behavior is described where useful to users.
- [ ] Examples are accurate and runnable in project context.

## References

- `pyllments/elements/llm_chat/llm_chat_element.py`
- `pyllments/elements/llm_chat/llm_chat_model.py`
- `docs/elements/LLMChatElement/index.qmd`
