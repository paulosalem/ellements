# CLAUDE.md — Ellements

## Project Overview

This repository is the **public Ellements core**. It publishes six packages under the shared `ellements.*` namespace:

- `ellements.core` — async-only `LLMClient`, multimodal inputs (`ImageInput`, `ImageURLPart`), `PersonaLibrary`, `GuidelineLibrary`, `TemplateRenderer`, observers (`LLMObserver`, `JsonlPromptLogger`), text helpers, simple-tool wrapping, exceptions (`MaxToolIterationsError`, `PromptKeyMissingError`, `StructuredOutputUnsupportedError`, `LogprobsUnsupportedError`, `PersonaNotFoundError`, `GuidelineNotFoundError`)
- `ellements.execution` — `Strategy` Protocol + `BaseStrategy`; strategies: `SingleCallStrategy`, `SelfConsistencyStrategy`, `ReflectionStrategy` (structured `CritiqueResult`), `TreeOfThoughtStrategy` (`mode={beam,dfs,simple}`, structured `Evaluation`), `CollaborativeEditingStrategy` (with `EditCallback` Protocol + `CallableEditCallback`/`FileEditCallback`/`PassthroughEditCallback`); `BUILTIN_STRATEGIES` registry
- `ellements.agents` — `AgentBackend` Protocol + `OpenAIAgentsBackend` and `ClaudeAgentsBackend`; `AgentController`, `ControllerConfig`, `AgentBuilder`
- `ellements.benchmarking` — single-loop async harness, `BenchmarkComparison`, `BenchmarkModel` (hard-fails at startup on logprob-incompatible tasks)
- `ellements.cli` — `components.py` building blocks, `CliPrinter` (pluggable event renderers), generic `AgentTUI` (parameterized `SaveHandler` + `EventRenderer` plugins)
- `ellements.fslm` — finite-state linguistic machines: explicit graph, deterministic kernel, NL evaluators, persistence, observers, `fslm` CLI


## Architectural Invariants

- **No backward compatibility.** Removed names are removed; never restore them.
- **Async-only public API.** No `*_sync` wrappers; if a caller needs sync, they wrap with `asyncio.run`.
- **`LLMClient(model=...)` is required at construction.** There is no default model anywhere in the public surface.
- **All LLM calls emit observer events.** `complete`, `complete_structured`, `complete_with_tools`, and `stream` all go through the same observer pipeline.
- **Retry lives on `LLMClient`** (litellm-exception-type-based, exponential backoff with full jitter, 3 attempts). Strategies must not double-retry.
- **`complete_with_tools` raises `MaxToolIterationsError`** carrying partial conversation + unresolved tool_calls when the iteration cap is hit.
- **Strategies validate prompts.** `BaseStrategy._get_prompt(key, required=True)` raises `PromptKeyMissingError`. No engine-side `STRATEGY_CLASS.REQUIRED_PROMPTS` introspection.

## UI/UX Design Directive

- Whenever implementing a UI (graphical or textual), always aim for the most beautiful, most gorgeous, most wonderful option that still remains elegant, sleek, and highly functional.

## Rule Synchronization Directive

- Whenever updating either `CLAUDE.md` or Copilot instruction files, always update the counterpart file(s) as part of the same change so behavior rules stay synchronized across assistants.

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

- `ellements-core/src/ellements/core/`
- `ellements-execution/src/ellements/execution/`
- `ellements-agents/src/ellements/agents/`
- `ellements-benchmarking/src/ellements/benchmarking/`
- `ellements-cli/src/ellements/cli/`
- `ellements-fslm/src/ellements/fslm/`
