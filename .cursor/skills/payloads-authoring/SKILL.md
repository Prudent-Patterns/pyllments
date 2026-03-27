---
name: payloads-authoring
description: Implements and updates Pyllments payload structures and usage contracts between elements. Use when adding payload types, changing payload schemas, or adjusting payload handling in ports and elements.
---

# Payloads Authoring

## Payload responsibilities

- Treat payloads as structured data contracts between elements.
- Keep payload schemas explicit and stable across connected ports.
- Ensure payload data is sufficient for receiving element behavior.

## Integration guidance

- Confirm emitters pack payload fields consistently.
- Confirm receivers validate and use payload fields safely.
- Keep payload evolution backward-aware where possible.

## Authoring checklist

- [ ] Payload structure is documented in code or docstrings.
- [ ] Sender and receiver expectations match.
- [ ] Port compatibility remains intact after schema changes.
- [ ] Tests cover common and edge-case payload paths.
