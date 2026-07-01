# Ellements — Architecture

This document describes how the **public** `ellements` library is laid out
today: which packages exist, what each one owns, how they depend on each
other, and where the extension seams live. It is written for two
audiences at once: humans who want to understand the project, and AI
programming agents who will keep extending it. Both should be able to
make changes confidently without re-reading every module.

---

## 1. Design principles

Three principles run end-to-end through the codebase. When in doubt,
optimize for these.

1. **Small, sharp public surface.** Every package exposes a tightly
   curated `__all__`. Anything not in `__all__` is internal and may
   change. The public surface is mostly **Protocols + a handful of
   concrete implementations**, so users can plug their own pieces in.
2. **No backward compatibility, no leftovers.** When something is
   renamed or moved, the old name is *deleted* — no aliases, no
   `__getattr__` shims, no deprecation warnings. The library is fresh.
   Migrations live in commit history, not in code.
3. **All-async LLM I/O.** Every method that touches a model is `async`.
   There are no `*_sync` siblings. Callers run inside an event loop, and
   tests use `pytest-asyncio`.

Supporting conventions:

* **Google-style docstrings** with `Args:` / `Returns:` / `Raises:`
  sections on every public symbol.
* **Modern typing**: `str | None`, `list[T]`, `dict[str, T]`, Protocols
  from `typing` (not `typing_extensions`).
* **mypy --strict clean** on every public package.
* **ruff clean** (`E, F, UP, B, SIM, I`).
* **Mustache templating** via `chevron` for any prompt string substitution.

---

## 2. Package map

The public library ships as five sibling Python packages under the
`ellements/` namespace:

```
ellements/
├── ellements-core           # primitives every other package depends on
├── ellements-execution      # prompting strategies (single-call, ToT, …)
├── ellements-agents         # agentic loops (OpenAI / Claude backends)
├── ellements-benchmarking   # offline eval harness for LLMs and strategies
├── ellements-cli            # generic terminal UI building blocks
└── ellements-fslm            # finite-state linguistic machines
```

Dependency direction is strictly one-way:

```
        ┌─────────────┐
        │    core     │  ← foundation: LLMClient, tools, prompts, observers
        └─────┬───────┘
              │
   ┌──────────┼─────────────┬──────────────┬────────┐
   ▼          ▼             ▼              ▼        ▼
execution   agents     benchmarking       cli      fslm
```

Nothing in `core` imports from any of the other packages. `execution`,
`agents`, `benchmarking`, `cli`, and `fslm` depend on `core` (and *only* on
core). They do not depend on each other.

---

## 3. `ellements-core` — the foundation

`core` is split into clearly-purposed subpackages. Every subpackage
gathers a coherent concept and exposes a small Protocol plus one or two
reference implementations.

```
ellements/core/
├── llm/              # LLMClient + Protocol, LLMClientWrapper base, messages, multimodal types
├── tools/            # Tool, ToolRegistry, ToolDialect, ToolExecutor
├── prompting/        # PersonaLibrary, GuidelineLibrary, PromptContext
├── templating/       # Mustache renderer (chevron)
├── observability/    # LLMObserver Protocol + JsonlPromptLogger
├── chunking/         # TextProcessor + count_tokens (tiktoken)
├── caching/          # Cache Protocol + InMemoryCache + JsonDiskCache
├── rate_limit/       # RateLimiterProtocol + TokenBucketRateLimiter
├── budgeting/        # BudgetTrackerProtocol + Call/Token budgets
├── config/           # load_json/load_toml + overlay merging
├── async_utils.py    # parallel_map helper
└── exceptions.py     # all domain-specific exception classes
```

### 3.1 `llm` — the model client

`LLMClient` is the single client class. It is **all-async** and exposes
four methods:

* `complete(messages, **kwargs) -> str`
* `complete_structured(messages, schema, **kwargs) -> BaseModel`
* `complete_with_tools(messages, tools, **kwargs) -> ToolCallResponse`
* `stream(messages, **kwargs) -> AsyncIterator[str]`

`model` is a **required** constructor argument — there is no global
default. Each method emits uniform observer events
(`on_request` / `on_response` / `on_error`).

Retries are handled inside `LLMClient` (3 attempts, exponential backoff
with full jitter, classified by litellm exception type — not by
substring matching). Strategies and agents never retry themselves.

`LLMClientProtocol` is the structural type that the rest of the codebase
depends on, so users can substitute their own client.

Multimodal inputs use `ImageInput` (`from_path` / `from_url` /
`from_data_uri`) which converts to `ImageURLPart` for the wire format.

### 3.2 `tools` — model-callable functions

The tool system has three layers:

1. **`Tool` / `SimpleTool`** — function objects with an arg schema.
2. **`ToolRegistry`** — collection that resolves names to implementations.
3. **`ToolDialect`** (Protocol) + concrete dialects:
   - `OpenAIChatDialect`
   - `OpenAIResponsesDialect`
   - `AnthropicDialect`
   - `GeminiDialect`

A dialect knows how to **serialize tool specs for the wire** *and* how to
**parse `tool_calls` back out of an assistant message** for a specific
provider. `default_dialect_for_model("gpt-4o")` picks the right one.
Adding a new provider = subclass `ToolDialect` + register it.

`ToolExecutor` runs tool calls and produces `ToolCallRecord` /
`ToolCallResponse` for downstream consumers. `MaxToolIterationsError`
carries the partial conversation when an agent loop runs over budget.

### 3.3 `prompting` — personas and guidelines

* `PersonaLibrary` and `GuidelineLibrary` both expose a single
  `load(name)` method.
* Both accept `.json` and `.md` files (YAML front-matter on persona
  markdown; `{name, text}` JSON for guidelines).
* `add_from_path(path)` adds new entries; id-collisions raise.
* `PromptContext` carries persona + guideline IDs through a call chain.

### 3.4 `observability` — uniform events

`LLMObserver` Protocol has three methods:
`on_request(LLMRequestEvent)`, `on_response(LLMResponseEvent)`,
`on_error(LLMErrorEvent)`. Every `LLMClient` method fires the matching
event. `JsonlPromptLogger` is a reference observer that writes
JSON-lines with full request/response/timing (async-safe via
`asyncio.Lock`, date-rollover at midnight). `format_log_markdown()`
re-renders a log into a human-readable Markdown view.

`AgentEvent` is the typed event surface that `ellements-agents`
publishes (and `ellements-cli` renders).

### 3.5 The composition layers

Three Protocol-based wrappers compose around any `LLMClientProtocol`:

| Subpackage   | Protocol               | Wrapper                | Purpose                                |
|--------------|------------------------|------------------------|----------------------------------------|
| `caching`    | `Cache`                | `CachingLLMClient`     | Skip the API on cache hit              |
| `rate_limit` | `RateLimiterProtocol`  | `RateLimitedLLMClient` | Throttle calls (token-bucket default)  |
| `budgeting`  | `BudgetTrackerProtocol`| `BudgetedLLMClient`    | Cap spend by calls or tokens           |

All three share the same shape: a `Protocol` for the strategy, a
default implementation (`InMemoryCache` / `TokenBucketRateLimiter` /
`CallCountBudget`+`TokenBudget`), and a wrapper that delegates to an
inner `LLMClientProtocol`. The three wrappers all inherit from
`LLMClientWrapper` (in `core.llm.wrapper`), which centralises the
"delegate every `LLMClientProtocol` method to an inner client" boilerplate
so individual wrappers only override the methods they actually augment.
They compose in any order:

```python
client = BudgetedLLMClient(
    RateLimitedLLMClient(
        CachingLLMClient(LLMClient(model="gpt-4o"), cache=InMemoryCache()),
        rate_limiter=TokenBucketRateLimiter(rate=5, capacity=10),
    ),
    tracker=CallCountBudget(limit=1000),
)
```

`BudgetedLLMClient` charges flat per-method costs (mirrors
`RateLimitedLLMClient`). For **token-accurate** budgeting, attach the
`TokenBudget` as an `LLMObserver` directly — `LLMResponseEvent.usage`
carries the input/output token counts. That choice is documented on
`BudgetedLLMClient` itself.

### 3.6 Exceptions

All public exceptions live in `core.exceptions` and derive from
`EllementsError`:

* `LLMError`, `ConversationError`, `ValidationError`
* `MaxToolIterationsError(conversation, unresolved_tool_calls)`
* `StructuredOutputUnsupportedError`, `LogprobsUnsupportedError`
* `PersonaNotFoundError`, `GuidelineNotFoundError`, `PromptKeyMissingError`
* `BudgetExceededError(limit, spent, attempted)`
* `ConfigError`

---

## 4. `ellements-execution` — prompting strategies

`execution` turns a single user prompt into an LLM-augmented answer.
Every strategy is structured the same way:

* A frozen `*StrategyConfig` Pydantic model holds the parameters.
* A `*Strategy` class wraps a `LLMClientProtocol` and exposes
  `async run(prompt, **kwargs) -> str`.
* All strategies implement the `Strategy` Protocol.

```
ellements/execution/
├── strategies.py        # Strategy Protocol + BaseStrategy
├── single_call.py       # SingleCallStrategy
├── self_consistency.py  # SelfConsistencyStrategy (n-of-k majority)
├── reflection.py        # ReflectionStrategy (structured CritiqueResult)
├── tree_of_thought.py   # TreeOfThoughtStrategy(mode={beam, dfs, simple})
├── collaborative.py     # CollaborativeEditingStrategy (uses EditCallback)
├── callbacks.py         # EditCallback Protocol + CallEditCallback + FileEditCallback
├── config.py            # base config types + stage_temperatures
└── catalog.py           # BUILTIN_STRATEGIES registry
```

Key design points:

* All prompt substitution goes through `core.templating.TemplateRenderer`
  (Mustache). No ad-hoc `str.replace`.
* `ReflectionStrategy` uses `complete_structured` with `CritiqueResult`
  (`is_satisfied`, `issues`). No keyword-scan parsing.
* `TreeOfThoughtStrategy` uses `complete_structured` with `Evaluation`
  (`score`, `reasoning`). `mode` selects between beam search, DFS, and
  a "simple" linearization.
* `stage_temperatures: dict[str, float] | None` is supported on every
  config so callers can tune individual stages.
* Tools (when the strategy supports them) are forwarded into
  `LLMClient.complete_with_tools`.
* `CollaborativeEditingStrategy` knows only about `EditCallback` — it
  does **not** import `subprocess`. `FileEditCallback` (in
  `callbacks.py`) does the editor invocation, using the safe list-form
  `subprocess.run([editor, str(path)], check=False)` via
  `asyncio.to_thread`.

---

## 5. `ellements-agents` — agentic loops

`agents` is the multi-turn reasoning layer. It's structured around
backend pluggability:

```
ellements/agents/
├── backend.py         # AgentBackend Protocol
├── openai_backend.py  # OpenAIAgentsBackend
├── claude_backend.py  # ClaudeAgentsBackend
├── controller.py      # AgentController + ControllerConfig
├── builder.py         # AgentBuilder (persona/guideline composition)
├── runner.py          # high-level run() entry point
├── tools.py           # agents-side wrappers around core.tools
└── prompts/           # the agent's own system prompts (Mustache)
```

`AgentBackend` is a Protocol with the shape:

```python
class AgentBackend(Protocol):
    async def turn(
        self,
        conversation: Conversation,
        tools: ToolRegistry,
        *,
        on_event: Callable[[AgentEvent], None],
    ) -> AgentTurnResult: ...
```

Each backend uses its provider's preferred control flow (OpenAI's
Responses API; Anthropic's tool-use cycle) but produces the same
`AgentTurnResult` and the same stream of `AgentEvent`s. The TUI in
`ellements-cli` consumes those events; it does not care which backend
produced them.

`AgentController` owns the conversation state, budget, and stop
conditions. `AgentBuilder` composes a personality from
`PersonaLibrary` + `GuidelineLibrary` and produces a configured
controller.

---

## 6. `ellements-benchmarking` — offline evaluation

```
ellements/benchmarking/
├── harness.py   # benchmark harness, owns the event loop
└── results.py   # result records + summary statistics
```

The harness owns **one persistent event loop**. Tasks that need
logprobs are validated up-front: incompatible models hard-fail at
startup rather than silently returning `0.0`. The litellm provider
prefix is preserved end-to-end. Progress callbacks fire for real
(not just at completion).

---

## 7. `ellements-cli` — generic terminal UI

```
ellements/cli/
├── components.py  # pure rich/textual building blocks
├── printer.py     # CliPrinter (with pluggable EventRenderer)
├── adapters.py    # AgentController → PersonaProvider/GuidelineProvider adapters
└── agent_tui.py   # generic AgentTUI (textual)
```

`AgentTUI` is **fully generic**:

* Callers supply a `SaveHandler` Protocol (no hardcoded save path).
* Callers supply an `EventRenderer` (no hardcoded event-name dispatch).
* Callers supply a `PersonaProvider` / `GuidelineProvider` for cockpit
  state — `adapters.py` ships ready-made adapters that bridge a
  `PersonaLibrary` + `GuidelineLibrary` + `AgentController` triple into
  those Protocols, so the TUI never imports `AgentController` directly.
* Modal state is an `enum`.
* Slash commands are declarative — registered, not hardcoded.

`CliPrinter` renders the same `AgentEvent` stream that
`ellements-agents` publishes, so any custom backend that emits well-
formed events plugs in for free.

App-specific widgets (e.g. PromptSpec's strategist tree) live in their
respective apps, not here.

---

## 8. `ellements-fslm` — finite-state linguistic machines

```
ellements/fslm/
├── models.py          # pydantic specs, events, snapshots, decisions
├── dsl.py             # fluent Python machine builder
├── det.py / nl.py     # deterministic and natural-language helper specs
├── definition.py      # executable MachineDefinition + RuntimeBindings
├── loading.py         # YAML/Python loading and binding resolution
├── kernel.py          # single-step deterministic kernel
├── evaluators.py      # LLM-backed semantic evaluators
├── persistence.py     # in-memory/local stores
├── observers.py       # FSLM event observers
├── visualization.py   # Mermaid output
└── cli.py             # fslm command
```

`fslm` exists for workflows where agentic behavior must stay bounded by an
explicit graph. The graph decides what is possible; deterministic code handles
crisp logic; natural-language evaluators handle semantic judgment. The
terminology is intentionally "linguistic" because prompts and language-backed
decisions are part of the runtime contract, not an afterthought. PromptSpec uses
this package directly for `@execute fslm`, so its public surface must stay
available from the main `ellements` distribution.

---

## 9. Extension points (the "where to hook in" cheat-sheet)

This section is the most important part of the document for anyone —
human or AI — adding a feature.

| You want to…                                  | Implement…                              | Wrap with…                                  |
|-----------------------------------------------|-----------------------------------------|---------------------------------------------|
| Swap the model client                         | `LLMClientProtocol`                     | Pass into strategies/agents directly        |
| Support a new provider's tool calling         | `ToolDialect`                           | Pass to `LLMClient(tool_dialect=…)`         |
| Cache LLM calls a new way                     | `Cache`                                 | `CachingLLMClient`                          |
| Throttle requests a new way                   | `RateLimiterProtocol`                   | `RateLimitedLLMClient`                      |
| Cap spend / count calls                       | `BudgetTrackerProtocol`                 | `BudgetedLLMClient`                         |
| Log calls a new way                           | `LLMObserver`                           | `LLMClient(observers=[…])`                  |
| Add a prompting strategy                      | `Strategy` Protocol                     | Register in `BUILTIN_STRATEGIES`            |
| Add an agent backend                          | `AgentBackend` Protocol                 | Pass to `AgentController`                   |
| Drive a different editor in CollaborativeEditing | `EditCallback` Protocol              | Pass to `CollaborativeEditingStrategy`      |
| Render agent events in a new UI               | `EventRenderer`                         | Pass to `CliPrinter` / `AgentTUI`           |
| Hand-off save target for the TUI              | `SaveHandler`                           | Pass to `AgentTUI`                          |
| Add finite-state workflow semantics           | `MachineSpec` / `MachineDefinition`     | Run through `FSLMKernel`                     |

When adding a new extension point, follow the established shape:

1. Define a `Protocol` in a small dedicated module.
2. Provide one reference implementation that's the "obvious" choice.
3. Document the Protocol with `Args:` / `Returns:` and a worked example.
4. Add a test that asserts conformance for the reference implementation.

---

## 10. Working in this codebase (for agents and humans)

### Test and lint loops

```bash
# Public ellements (run from ellements/)
unset OPENAI_API_KEY ANTHROPIC_API_KEY
python -m pytest -q
python -m ruff check
python -m mypy --strict ellements-core/src ellements-execution/src \
                ellements-agents/src ellements-benchmarking/src \
                ellements-cli/src ellements-fslm/src
```

All checks must be green before committing.

### Style rules (enforced)

* All-async public API. No `*_sync` helpers.
* Google-style docstrings on every public symbol.
* No `__getattr__` shims. No alias methods. No deprecation warnings.
* `dict` / `list` / `X | Y` everywhere. No `typing.Dict` / `typing.List`.
* `pyupgrade --py311-plus` + `ruff --fix` before committing.

### Where to add things

### Naming conventions

* Strategies end in `Strategy` (`SingleCallStrategy`, not `SingleCall`).
* Configs end in `Config` and are immutable Pydantic models.
* Protocols are named after the role
  (`Cache`, `LLMClientProtocol`, `Strategy`). When the role name would
  collide with an obvious concrete implementation name in the same
  subpackage we explicitly suffix the Protocol with `Protocol` to
  disambiguate (e.g. `RateLimiterProtocol` next to
  `TokenBucketRateLimiter`; `BudgetTrackerProtocol` next to
  `CallCountBudget`). Prefer the bare role name when there's no clash.
* Methods are verbs (`load`, not `get_persona`). The single canonical
  verb is chosen and there are no aliases.
