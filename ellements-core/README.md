# ellements-core

`ellements-core` contributes the `ellements.core` import package to the single
`ellements` distribution. It is the foundation layer: model calls, messages,
tools, prompt context, observability, optional client wrappers, and shared
exceptions.

## Principles

- **Explicit model calls.** `LLMClient(model=...)` is required. There is no
  hidden default model.
- **Protocols before inheritance.** Consumers should depend on
  `LLMClientProtocol`, `Tool`, `Cache`, `RateLimiterProtocol`, or
  `BudgetTrackerProtocol` when they only need behavior.
- **Composition wrappers.** Caching, rate limiting, and budgeting wrap a client;
  the base `LLMClient` stays focused on provider I/O.
- **One canonical tool surface.** Tools become `ToolSpec` records in a
  `ToolRegistry`; provider dialects translate them at the edge.
- **Observers, not ad hoc logging.** LLM calls emit structured request,
  response, and error events. `JsonlPromptLogger` is the reference observer.
- **Small public root.** `ellements.core` re-exports the happy path; specialized
  mechanisms live under their owning subpackages.

## Structure

| Module | Role |
| --- | --- |
| `ellements.core.llm` | `LLMClient`, conversations, multimodal messages, structured output, streaming, tool calls, image generation |
| `ellements.core.tools` | `ToolRegistry`, `SimpleTool`, provider dialects, tool-call records |
| `ellements.core.prompting` | `PromptContext`, `PersonaLibrary`, `GuidelineLibrary` |
| `ellements.core.observability` | LLM/agent events, `LLMObserver`, `JsonlPromptLogger`, Markdown formatting |
| `ellements.core.caching` | `CachingLLMClient`, `InMemoryCache`, `JsonDiskCache` |
| `ellements.core.rate_limit` | `RateLimitedLLMClient`, `TokenBucketRateLimiter` |
| `ellements.core.budgeting` | `BudgetedLLMClient`, call-count and token budgets |
| `ellements.core.config`, `chunking`, `templating`, `async_utils` | Small reusable utilities |

## Examples

```python
from ellements.core import JsonlPromptLogger, LLMClient

client = LLMClient(
    model="openai/gpt-4.1",
    observers=[JsonlPromptLogger("./logs")],
)

answer = await client.complete("Summarize model checking in one paragraph.")
```

```python
from ellements.core import LLMClient, ToolRegistry


def lookup(symbol: str) -> str:
    """Return a short description for a ticker symbol."""
    return f"{symbol}: placeholder company description"


client = LLMClient(model="openai/gpt-4.1")
tools = ToolRegistry({"lookup": lookup})

response = await client.complete_with_tools(
    "What does ACME do? Use tools if needed.",
    tools=tools,
)
print(response.content)
print(response.tool_calls)
```

```python
from ellements.core import LLMClient
from ellements.core.caching import CachingLLMClient, InMemoryCache
from ellements.core.rate_limit import RateLimitedLLMClient, TokenBucketRateLimiter

base = LLMClient(model="openai/gpt-4.1")
cached = CachingLLMClient(inner=base, cache=InMemoryCache(default_ttl=3600))
client = RateLimitedLLMClient(
    inner=cached,
    limiter=TokenBucketRateLimiter(rate_per_second=2.0, capacity=4),
)
```

## Extending

Add stable primitives here when more than one package should be able to reuse
them. Prefer a small protocol plus one obvious implementation; keep provider
wire formats behind dialects; and do not hide behavior in broad root exports.
