<p align="center">
  <img src="./ellements_logo_transparent_crisp.png" alt="Ellements logo" width="360">
</p>

<h1>Ellements</h1>

<p >
  <strong>A Python toolkit for extreme experimentation with LLM systems.</strong>
</p>

**Ellements** is best understood as a continuously extended set of building
blocks for LLM experimentation: model clients, prompt context, execution
strategies, agent abstractions, benchmarking harnesses, and terminal UI
primitives. The repository is organized into focused source roots, but ships as
a single PyPI package, `ellements`, containing every public `ellements.*`
subpackage.

> [!WARNING]
> **Do not treat this as a normal dependency.** This repository exists to support
> my own projects, experiments, and tooling. Probably nobody other than me should
> depend on it directly.

> [!NOTE]
> Almost all of it is created with AI assistance, and I myself understand only a
> fraction of it at any given time. This can produce fast-paced changes, as well
> as both good and bad surprises. Pull requests are unlikely to be accepted. This
> is published for transparency and my own reuse, not as a community-maintained
> library or a general-purpose package roadmap.

## Why yet another LLM library?

True, there are many other similar libraries. This one, however, is mine. It exists so I can keep extending it,
test ideas, change direction, delete abstractions, and rebuild APIs as I see fit:
not by committee, not by roadmap, not by community consensus.

## Design principles

The practical consequences are the following:

- **One install, focused internals.** `pip install ellements` installs the full
  namespace: `ellements.core`, `ellements.execution`, `ellements.agents`,
  `ellements.benchmarking`, `ellements.cli`, `ellements.domain_specific`,
  `ellements.reporting`, `ellements.standard_tools`, and `ellements.fslm`.
- **Extension before stabilization.** The point is to keep adding mechanisms as
  they become useful in my projects. Stability comes later, if it comes at all.
- **Async-only public API.** No hidden sync wrappers. Callers keep explicit
  control of concurrency.
- **Explicit model selection.** `LLMClient(model=...)` is required. There is no
  hidden default.
- **Explicit local caching.** Pass `LocalCacheConfig(directory=...)` to cache
  exact text/Responses calls through LiteLLM and image generation/edit responses
  through Ellements' content-addressed disk cache. URL-only image responses are
  not persisted because provider URLs expire. Caching is off when omitted.
- **Structured observability.** Every LLM call emits request, response, and
  error events. `JsonlPromptLogger` writes durable JSON-lines traces.
- **Composable strategy layer.** Single-call, reflection, self-consistency,
  tree-of-thought, and collaborative editing all conform to one `Strategy`
  protocol.
- **Backend-agnostic agents.** `ellements.agents` is an abstraction layer over
  external agent libraries. OpenAI Agents and Claude Agents are adapters; they
  are not the identity of the module.
- **Finite-state linguistic machines.** `ellements.fslm` keeps agentic workflows
  bounded by explicit state graphs while still allowing natural-language guards,
  invariants, actions, and outputs where they are useful. The `L` is deliberate:
  language is part of the control surface, not a decorative interface.

## Install

```bash
pip install ellements
```

Optional extras install integration-specific dependencies. They do **not** split
the package or change which modules ship in the wheel.

```bash
pip install "ellements[agents]"        # declared agent-adapter dependencies
pip install "ellements[benchmarking]"  # lm-eval integration
pip install "ellements[cli]"           # Textual-powered terminal UI helpers
pip install "ellements[fslm]>=0.2.0"   # finite-state linguistic machines
pip install "ellements[finance]"       # Yahoo Finance asset tools
pip install "ellements[web]"           # web search, crawl, and YouTube tools
pip install "ellements[reporting]"     # chart/report export helpers
pip install "ellements[all]"           # all declared optional integrations
```

In particular, the agents module is not OpenAI-specific. It defines shared
builder, controller, runner, and event abstractions over external agent
libraries. The OpenAI adapter has declared optional dependencies; the Claude
adapter is included in the wheel, but its upstream SDK is still evolving, so
install it separately when using that backend.

## What ships

| Import package | Purpose |
| --- | --- |
| `ellements.core` | `LLMClient`, conversations, multimodal inputs, tools, prompt context, templating, observers, caching, rate limiting, budgeting, and config helpers |
| `ellements.execution` | Prompting strategies: `SingleCallStrategy`, `ReflectionStrategy`, `SelfConsistencyStrategy`, `TreeOfThoughtStrategy`, `CollaborativeEditingStrategy` |
| `ellements.agents` | Backend-agnostic layer over external agent libraries: runner, controller, fluent `AgentBuilder`, event surface, and OpenAI/Claude adapters |
| `ellements.benchmarking` | Async benchmark harnesses, model runners, dataset adapters, and comparison helpers |
| `ellements.cli` | Terminal presentation primitives, agent TUI components, and slash-command building blocks |
| `ellements.domain_specific` | Domain tools, currently including finance calculators, Yahoo Finance asset data, valuation, technical indicators, and risk helpers |
| `ellements.reporting` | Chart artifacts, HTML report generation, and multi-format presentation helpers |
| `ellements.standard_tools` | Reusable tool surfaces for terminal execution, web search, web crawl/read, and YouTube search/transcript access |
| `ellements.fslm` | Finite-state linguistic machines: explicit graphs, deterministic kernel, natural-language evaluators, persistence, observers, and `fslm` CLI |

## Quick start

```python
import asyncio

from ellements.core import JsonlPromptLogger, LLMClient, LocalCacheConfig


async def main() -> None:
    client = LLMClient(
        model="openai/gpt-5.5",
        observers=[JsonlPromptLogger("./logs")],
        local_cache=LocalCacheConfig("./cache"),
    )

    answer = await client.complete("Explain attention in one paragraph.")
    print(answer)


asyncio.run(main())
```

## Use OpenRouter

`LLMClient` also supports [OpenRouter](https://openrouter.ai) through the same
LiteLLM path as direct OpenAI, Anthropic, and other providers. No additional SDK
or package extra is needed: set `OPENROUTER_API_KEY` and prefix an
[OpenRouter model ID](https://openrouter.ai/models) with `openrouter/`.

```bash
export OPENROUTER_API_KEY="your-openrouter-api-key"
```

```python
import asyncio

from ellements.core import LLMClient


async def main() -> None:
    client = LLMClient(model="openrouter/openai/gpt-4.1-mini")
    print(await client.complete("Explain attention in one paragraph."))


asyncio.run(main())
```

OpenRouter is useful when comparing models from different vendors through one
account, experimenting with price/latency tradeoffs, or using its provider
routing and fallbacks for availability. Your Ellements strategies and client
wrappers stay unchanged. Model capabilities, pricing, and data-handling policies
still depend on the chosen model and upstream provider.

See the [core provider guide](ellements-core/README.md#providers-and-openrouter)
for explicit credentials, optional app headers, routing preferences, streaming,
and structured output.

## Run a strategy

```python
from ellements.execution import ReflectionConfig, ReflectionStrategy

strategy = ReflectionStrategy()

result = await strategy.execute(
    prompts={
        "generate": "Draft a haiku about distributed systems.",
        "critique": "Review this draft and return a CritiqueResult:\n\n{{response}}",
        "revise": (
            "Revise the draft using the issues below.\n\n"
            "Draft:\n{{response}}\n\nIssues:\n{{issues}}"
        ),
    },
    client=client,
    config=ReflectionConfig(max_rounds=3),
)

print(result.output)
```

Runtime strategy templates accept both Mustache placeholders such as
`{{response}}` and PromptSpec-style placeholders such as `@{response}`.

## Build an agent

OpenAI is shown here as one concrete adapter; the builder targets the
backend-agnostic `AgentBackend` protocol.

```python
from ellements.agents import AgentBuilder, OpenAIAgentsBackend

agent = (
    AgentBuilder("researcher", backend=OpenAIAgentsBackend())
    .with_model("gpt-4.1")
    .with_instructions("Research carefully, cite evidence, and be concise.")
    .with_tool("search", my_search_tool)
    .build()
)
```

## Use finance and web tools

Finance and web tools expose canonical `ToolRegistry` surfaces, so LLM clients,
agents, and PromptSpec examples can bind the same tools without local adapters.

```bash
pip install "ellements[finance,web]"
playwright install chromium  # required by crawl4ai-backed page crawling
```

```python
from ellements.domain_specific.finance.yahoo_finance import finance_tools
from ellements.standard_tools.web.crawler import web_crawler_tools
from ellements.standard_tools.web.search import web_search_tools

tools = (
    finance_tools()
    .merge(web_search_tools())
    .merge(web_crawler_tools(max_content_tokens=4000))
)

print(sorted(tools))
```

Typical stock-research tools include `search_asset`, `get_asset_quote`,
`get_asset_profile`, `get_financial_metrics`, `search_web`, `search_news`, and
`crawl_url`.

## Packaging model

The repo is modular at the filesystem level:

```text
ellements-core/src/ellements/core
ellements-execution/src/ellements/execution
ellements-agents/src/ellements/agents
ellements-benchmarking/src/ellements/benchmarking
ellements-cli/src/ellements/cli
ellements-domain-specific/src/ellements/domain_specific
ellements-fslm/src/ellements/fslm
ellements-reporting/src/ellements/reporting
ellements-standard-tools/src/ellements/standard_tools
```

Those source roots are discovered into a single wheel,
`ellements-<version>-py3-none-any.whl`. Users install one PyPI project and
import the modules they need:

```python
from ellements.core import LLMClient
from ellements.domain_specific.finance.yahoo_finance import finance_tools
from ellements.execution import TreeOfThoughtStrategy
from ellements.agents import AgentBuilder
from ellements.fslm import FSLMKernel
from ellements.standard_tools.web.search import web_search_tools
```

This gives the repo clean internal boundaries without creating multiple PyPI
entries to publish, document, secure, and maintain.

## Local development

```bash
pip install -e ".[dev,all]"
python -m pytest -q
python -m ruff check .
python -m mypy --strict ellements-core/src ellements-execution/src \
  ellements-agents/src ellements-benchmarking/src ellements-cli/src \
  ellements-domain-specific/src ellements-fslm/src ellements-reporting/src \
  ellements-standard-tools/src
```

## License

MIT, with the project status and maintenance notice in [`LICENSE`](LICENSE).
