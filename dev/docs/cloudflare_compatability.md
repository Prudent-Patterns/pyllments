# Cloudflare Compatibility Plan

This document is the working architectural reference for making `pyllments` usable in Cloudflare Workers with Python on Pyodide, while preserving the framework's current structure and developer experience as much as possible.

The main design principle is to keep the existing Element/Model architecture intact, while making the runtime surface area smaller, more modular, and more explicit. In practice, this means distinguishing between:

- headless framework logic that should remain available in a lightweight Cloudflare install,
- optional UI and server features that are valuable for prototyping but not required in Workers,
- integrations whose current implementation depends on runtime features that do not map cleanly onto Pyodide.

## Layer 1: Overarching Concerns

### 1. Packaging Must Reflect Runtime Reality

The package currently presents a broad default install, but Cloudflare Workers only need a focused subset of the framework. The default dependency set should describe the minimal headless runtime, while heavier capabilities should move behind extras.

This is not only an optimization concern. In a Pyodide environment, dependency shape directly affects whether the package can be installed at all, how large the deployed bundle becomes, and how much initialization cost is paid at deploy time.

### 2. Import Boundaries Must Match Architectural Boundaries

Architecturally, models usually hold the core logic and do not depend on Panel. However, many import paths still pull in Panel-backed element or payload modules at import time. This makes Panel behave like a core dependency even when the user does not intend to create views.

The framework should preserve the current model/view split, but its import structure must be tightened so headless usage remains genuinely headless.

### 3. Worker Compatibility Requires a Supported Runtime Subset

Not every feature of `pyllments` needs to be fully functional in a lightweight Cloudflare deployment. The goal is not to force the whole framework into the smallest runtime tier. The goal is to define a clear compatibility surface:

- what must work in a lightweight Worker install,
- what should remain available behind extras,
- what must be redesigned before it can be considered Worker-compatible.

### 4. Good Design Is More Important Than Short-Term Hacks

We do not want a Worker port that only functions through scattered special cases. The refactor should reinforce the intended architecture:

- models remain the primary business-logic layer,
- elements remain the orchestration layer,
- views remain optional helpers for prototyping and local GUI workflows,
- integrations with stronger runtime assumptions are isolated instead of leaking into the whole package.

### 5. Async Behavior Must Be Simplified for a WASM Runtime

Cloudflare Workers and Pyodide favor a cleaner async model than the current mix of background tasks, lifecycle hooks, thread pools, subprocess handling, and sync-to-async bridging. Even where features remain conceptually supported, runtime management will need to become more explicit and less dependent on CPython process semantics.

## Layer 2: Module-Level Concerns

### 1. Core Package Surface

The root package and commonly used convenience imports should become safe for lightweight installations. A user should be able to import the framework's headless pieces without unintentionally loading Panel, FastAPI serving code, or other heavy integrations.

Primary concerns:

- `pyllments.__init__` should not eagerly import serve-time functionality.
- Package-level exports should not automatically force UI-backed modules into memory.
- The default public surface should align with the lightweight tier.

### 2. Element and Payload Boundaries

The architectural boundary between model logic and view logic already exists in spirit, but not consistently in import behavior. Elements and payloads should remain part of the framework, but their view-related dependencies should be optional at import time whenever possible.

Primary concerns:

- Models should stay importable without Panel.
- Element modules should avoid making Panel a hard requirement unless a view is actually used.
- Payload imports should not force Panel-backed payload classes when only model logic is needed.

### 3. UI and Serving Stack

Panel, Bokeh, and serving-related integrations are valuable for local prototyping and GUI-oriented workflows, but they should be treated as optional tooling rather than a baseline runtime requirement for Workers.

Primary concerns:

- Panel-backed views should remain supported in a dedicated UI tier.
- Panel-serving and FastAPI-serving concerns should not define the baseline dependency story.
- Lightweight Cloudflare installs should not carry GUI/server overhead unless explicitly requested.

### 4. LLM and Headless Flow Execution

The LLM-oriented portion of the framework is one of the most important pieces to preserve in Cloudflare. Headless flows involving ports, payloads, models, and LiteLLM-based generation should remain first-class.

Primary concerns:

- LiteLLM-backed chat elements are part of the critical Worker-safe target.
- Message and structured payload flows should continue to work without GUI requirements.
- Async message generation should be reviewed to ensure it maps cleanly onto Worker execution.

### 5. MCP Compatibility

MCP is strategically important, but its current implementation assumes subprocess management and thread-backed execution patterns that are not a good fit for Pyodide.

Primary concerns:

- subprocess-based MCP transport is not Worker-friendly,
- thread pool execution and sync fallbacks should be reconsidered,
- MCP support likely needs a Worker-specific transport and lifecycle model.

### 6. Runtime and Lifecycle Management

The runtime layer currently makes assumptions that are natural in a long-lived server process but less appropriate in Workers. Signal handlers, `atexit`, and cross-loop coordination need to be reconsidered as part of the compatibility effort.

Primary concerns:

- event loop ownership should be simpler and more predictable,
- cleanup should not depend on POSIX process behavior,
- APIs that block synchronously on async work should be minimized or isolated.

### 7. Integration Tiers

Some integrations should remain supported, but they do not all belong in the same installation tier.

Likely grouping:

- critical lightweight tier: core framework pieces, payload models, ports, LLM execution,
- optional production integrations: API-style or Worker-safe network integrations,
- optional local/server integrations: Panel serving, FastAPI server workflows,
- advanced redesign tier: MCP, Discord, Telegram, and other runtime-sensitive integrations.

## Layer 3: Detailed Workstreams

### 1. Define Installation Tiers

We should formalize package tiers so the dependency story becomes intentional.

Suggested target tiers:

- `core`: the minimal headless framework intended to install cleanly in Cloudflare Workers,
- `llm`: LiteLLM and other essentials for model-driven flows,
- `ui`: Panel and Bokeh for local prototyping and visualization,
- `serve`: FastAPI and serving helpers,
- `mcp`: MCP-specific support,
- `integrations`: Discord, Telegram, and similar external service connectors,
- `full`: the umbrella install for local power users.

Key outcome:

- the default install becomes small and Worker-oriented,
- optional capabilities remain available without being forced on every environment.

### 2. Make Panel Optional by Import Strategy, Not by Architecture Rewrite

The goal is not to remove views from the framework. The goal is to ensure that views are only required when views are actually used.

Detailed direction:

- remove eager root-level imports of serving helpers,
- avoid package exports that immediately import Panel-backed classes,
- consider lazy imports inside view methods or view-adjacent helpers,
- preserve the current Element/Model pattern rather than introducing a new abstraction layer unless necessary.

Key outcome:

- a developer can use the framework headlessly without installing Panel,
- Panel remains available for prototyping with minimal conceptual change.

### 3. Identify the Worker-Safe Element Set

All elements may remain part of the project, but they do not all need to function in the lightweight Cloudflare tier on day one.

Priority element classes:

- critical to keep working:
  - LLM chat and message-oriented flows,
  - context-building and history-oriented headless logic where feasible,
  - structured output and schema-driven flows where dependencies remain lightweight,
  - text and routing components where their core logic is not GUI-bound.
- keep but treat as optional:
  - view-heavy prototyping elements,
  - file or retrieval paths that depend on heavier optional packages.
- keep but redesign before Worker support:
  - MCP elements with subprocess assumptions,
  - platform integrations tied to long-lived client behavior.

Key outcome:

- compatibility becomes explicit and staged instead of all-or-nothing.

### 4. Refactor MCP Around Worker-Friendly Execution

MCP should remain a target, but likely through a different operational model than the current subprocess-centric implementation.

Detailed direction:

- separate MCP protocol abstractions from transport/runtime concerns,
- isolate subprocess-backed MCP for local/full installs,
- define a Worker-safe MCP mode that avoids subprocesses, thread pools, and process cleanup hooks,
- revisit tool execution so async-first flows are the default.

Key outcome:

- MCP remains part of the long-term architecture instead of being dropped,
- Worker compatibility becomes a transport and lifecycle problem to solve directly.

### 5. Simplify Runtime Ownership

The framework should avoid relying on process-style lifecycle management in environments that do not behave like normal Python processes.

Detailed direction:

- reduce reliance on `signal`, `atexit`, and forced shutdown logic,
- reevaluate sync wrappers that call into async internals,
- clarify which code owns the event loop in each deployment mode,
- prefer explicit async APIs in Worker-facing paths.

Key outcome:

- fewer hidden assumptions,
- cleaner portability between local servers, notebooks, and Workers.

Adopted runtime decisions for this workstream:

- keep the existing queue-backed `OutputPort` contract as the single default behavior across environments,
- slim lifecycle management to explicit async primitives (`drain` and `shutdown`) rather than POSIX signal/`atexit` hooks,
- keep server teardown on FastAPI lifespan hooks instead of runtime-level signal handlers,
- keep loop ownership simple and generic (single asyncio loop via existing runtime behavior),
- keep unsupported integrations importable and fail fast at runtime with clear errors.

### 6. Preserve Developer Experience Across Modes

A developer should not have to learn two different frameworks just because one deployment target is Cloudflare. The same concepts should remain valid across local prototyping and lightweight production.

Detailed direction:

- preserve Element/Model mental models,
- preserve Panel-based prototyping where useful,
- document which installs and imports are intended for which runtime tiers,
- ensure unsupported features fail clearly rather than implicitly.

Key outcome:

- the framework remains coherent even as its runtime surface becomes more modular.

## Architectural Target State

The intended end state is a framework with one architecture but multiple runtime tiers:

- a lightweight Cloudflare-oriented headless tier,
- a richer local prototyping tier with Panel and GUI helpers,
- a fuller local/server tier with serving and runtime-heavy integrations,
- a redesigned advanced tier for MCP and other runtime-sensitive features.

This keeps the framework unified while acknowledging that different execution environments should not be forced to carry the same dependency and lifecycle burden.

## Immediate Planning Priorities

The first concrete planning sequence should be:

1. define the lightweight install target and its required elements,
2. identify import paths that currently force Panel or serving code into headless usage,
3. redesign packaging tiers around that boundary,
4. isolate MCP and lifecycle concerns into an explicit later workstream,
5. validate the Worker-safe subset before expanding the compatibility surface.

## Staged Todo

This is the high-level order of operations to follow as the compatibility work proceeds. It is intentionally broad enough to guide architectural decisions, while still being concrete enough to keep the work scoped and staged.

1. Confirm the existing architecture can be preserved.
   The first priority is to verify that the current Element, Model, Payload, and Port design does not require a full architectural rewrite for Cloudflare compatibility. The working assumption is that the model-port-flow structure should remain intact, and that most of the necessary change belongs at the dependency, import, and runtime-management boundaries.

2. Define the lightweight Cloudflare-compatible runtime surface.
   We should explicitly identify which parts of the framework must work in a minimal install, especially the headless flow system, payload models, core ports, and critical LiteLLM-backed LLM paths. This gives us a concrete target before we begin changing packaging or internals.

3. Separate optional features from required features.
   Once the lightweight target is defined, we should classify the rest of the framework into categories: keep in the lightweight tier, keep behind extras, or keep but redesign for Worker compatibility. This should let us preserve all elements in the project without requiring every integration to function in the minimal Cloudflare environment.

4. Remove import-time coupling that violates the intended architecture.
   The next focus should be import safety. If models are intended to be headless, then import paths should reflect that. This means reducing or eliminating cases where Panel, serving code, or other heavy integrations are imported before a view or server path is actually used.

5. Redesign packaging around runtime tiers.
   After the import boundaries are clear, the dependency layout should be changed to match them. The package should expose a small core install and then layer on UI, serving, MCP, and integration capabilities through extras, rather than shipping all of them by default.

6. Rework lifecycle and async management where Worker assumptions differ.
   Lifecycle management, loop ownership, cleanup behavior, sync-to-async bridges, and other runtime-sensitive utilities should then be reviewed as a focused workstream. This is likely the area where the deepest technical changes will be needed, but ideally without changing the top-level framework concepts.

7. Treat MCP as a dedicated compatibility project inside the broader effort.
   MCP is important enough that it should not be treated as an afterthought, but it also should not block the first compatibility tier. The right approach is to preserve MCP as a target while acknowledging that its current subprocess and thread-oriented behavior may require a more substantial redesign than the rest of the framework.

8. Validate the result incrementally rather than aiming for total compatibility at once.
   Each tier should be validated before the next one expands the scope. The initial success condition is not that every feature works in Cloudflare immediately. The initial success condition is that the framework has a clean, lightweight, Worker-safe subset and a clear path for bringing more advanced capabilities along afterward.

## Questions This Todo Sequence Is Meant To Answer

- Can the framework remain structurally the same while becoming Cloudflare-compatible?
- Which parts of the framework belong in the minimal Worker-safe tier?
- Which parts should remain optional rather than be removed?
- Which parts need targeted redesign instead of simple packaging changes?
- How can lifecycle and async behavior be simplified without undermining the port-driven architecture?

## Working Assumptions

- Panel is worth keeping as a prototyping and developer-facing UI tool.
- Panel should not define whether the framework can be used in Workers.
- LiteLLM-backed LLM flows are part of the critical compatibility target.
- MCP is important enough to preserve, but not necessarily in its current implementation form.
- Not every existing integration needs to be available in the minimal Cloudflare install.
