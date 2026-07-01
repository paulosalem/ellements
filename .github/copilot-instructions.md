# Copilot Instructions — Ellements

## Project Overview

This repository is the **public Ellements core**, publishing six packages under the shared `ellements.*` namespace:

- `ellements.core` — async-only `LLMClient`, multimodal inputs, persona/guideline libraries, `TemplateRenderer`, observers (`JsonlPromptLogger`), text helpers, simple-tool wrapping, public exception hierarchy
- `ellements.execution` — `Strategy` Protocol + `BaseStrategy`; `SingleCallStrategy`, `SelfConsistencyStrategy`, `ReflectionStrategy` (structured `CritiqueResult`), `TreeOfThoughtStrategy` (`mode={beam,dfs,simple}`, structured `Evaluation`), `CollaborativeEditingStrategy` (with `EditCallback` Protocol); `BUILTIN_STRATEGIES` registry
- `ellements.agents` — `AgentBackend` Protocol with `OpenAIAgentsBackend` and `ClaudeAgentsBackend`; `AgentController`, `AgentBuilder`
- `ellements.benchmarking` — single-loop async harness with logprob-aware metrics
- `ellements.cli` — reusable `CliPrinter`, generic `AgentTUI` with plugin-based renderers and save handlers
- `ellements.fslm` — finite-state linguistic machines: explicit graph, deterministic kernel, NL evaluators, persistence, observers, `fslm` CLI


## Architectural Invariants

- **No backward compatibility, no leftovers.** Every change is a clean break. Do not reintroduce removed names, alias methods, family stub modules, or `_LEGACY_EXPORTS` blocks.
- **Async-only.** No `*_sync` wrappers anywhere.
- **`LLMClient(model=...)` is required.** No default model. No `default_model=` kwarg.
- **Uniform observers.** Every LLM-call method emits `LLMRequestEvent`/`LLMResponseEvent`/`LLMErrorEvent` to attached `LLMObserver`s.
- **Retry centralized on the client.** Strategies must not retry; they delegate to `LLMClient`'s litellm-exception-typed retry with exponential backoff + full jitter.
- **`complete_with_tools` raises `MaxToolIterationsError`** carrying partial conversation + unresolved tool calls on cap.
- **Strategies validate their own prompts** via `BaseStrategy._get_prompt(key, required=True)` raising `PromptKeyMissingError`.
- **Structured output for structured decisions.** Reflection uses `CritiqueResult`; ToT evaluation uses `Evaluation`. No string-pattern parsing.

## UI/UX Design Directive

- Whenever implementing a UI (graphical or textual), always aim for the most beautiful, most gorgeous, most wonderful option that still remains elegant, sleek, and highly functional.

## Rule Synchronization Directive

- Whenever updating either Copilot instruction files or `CLAUDE.md`, always update the counterpart file(s) as part of the same change so behavior rules stay synchronized across assistants.

## Public-Surface Discipline

- Do not add new public modules here unless they belong to one of the six existing packages.
- Preserve the `ellements.*` namespace; never expose internal modules through the public `__init__.py` files.

## Test Commands

```bash
python -m pytest \
  ellements-core/tests \
  ellements-execution/tests \
  ellements-agents/tests \
  ellements-benchmarking/tests \
  ellements-cli/tests \
  ellements-fslm/tests -q
```

Strict static analysis:

```bash
ruff check .
mypy --strict ellements-core/src ellements-execution/src ellements-agents/src \
              ellements-benchmarking/src ellements-cli/src ellements-fslm/src
```

## Key Areas

- `ellements-core/src/ellements/core/` — LLM client, multimodal inputs, prompting context, observers, simple tools, exceptions, templating
- `ellements-execution/src/ellements/execution/` — strategies, configs, callbacks, registry
- `ellements-agents/src/ellements/agents/` — backend-agnostic agent runner, builder, two concrete backends
- `ellements-benchmarking/src/ellements/benchmarking/` — async harness, comparison/model wrappers
- `ellements-cli/src/ellements/cli/` — components, printer, generic TUI
- `ellements-fslm/src/ellements/fslm/` — finite-state linguistic machines, kernel, DSL, persistence, observers
