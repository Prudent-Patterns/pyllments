---
name: views-authoring
description: Implements and refines Pyllments component views with Panel and Component.view patterns. Use when creating or modifying element or payload views, view watchers, or associated CSS-backed UI behavior.
---

# Views Authoring

## View design goals

- Keep view methods focused on presentation and user interaction.
- Use Panel objects and project component view patterns consistently.
- Keep styling concerns in CSS files where practical.

## Reactivity guidance

- Use project watcher patterns so refresh and recreation are safe.
- Ensure watcher side effects are idempotent and predictable.
- Route business decisions to model methods when possible.

## Authoring checklist

- [ ] Views are defined with project view decorators/patterns.
- [ ] UI state updates are cleanly connected to model/element state.
- [ ] Watchers are attached via project-safe lifecycle methods.
- [ ] CSS and structural view code remain maintainable.
