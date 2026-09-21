# ellements-core

`ellements-core` contributes the `ellements.core` import package to the single
`ellements` distribution. It is the foundation layer: model calls, messages,
tools, prompt context, observability, optional client wrappers, and shared
exceptions.

## Principles

Reference-assisted paid producers can inject `image_edit_transport` into
`LLMClient` and call `edit_image` with captured `(filename, bytes)` inputs.
`OpenAIImageEditTransport` uses the official async SDK, retains observed request
identities and upload hashes, and supports one high-fidelity opaque PNG result.
This transport requires client retries and caching to be disabled. Masks,
URLs, hidden conditioning and fallback to generation are unsupported. Transport
availability and input hashes establish neither reference permission nor custody;
the caller must establish those before financial admission and recheck at handoff.

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
| `ellements.yaml` | Lightweight safe YAML parsing with portable values and diagnostics |
| `ellements.core.config`, `chunking`, `templating`, `async_utils` | Small reusable utilities |

`ellements.yaml.load_yaml(content)` accepts text or bytes and retains
PyYAML's safe values, encoding behavior and Python diagnostics. It uses the
safe C parser where those semantics agree, without caching source contents or
constructed objects. Its lightweight root module does not load the model-provider
integrations. File ownership, current-byte reads and schema validation remain
the caller's responsibility.

## Providers and OpenRouter

Select a provider using LiteLLM's model identifier, not a separate client class.
For example:

| Route | Model example | Environment variable |
| --- | --- | --- |
| Direct OpenAI | `openai/gpt-4.1-mini` | `OPENAI_API_KEY` |
| Direct Anthropic | `anthropic/claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenRouter | `openrouter/openai/gpt-4.1-mini` | `OPENROUTER_API_KEY` |

For OpenRouter, the form is **`openrouter/<OpenRouter model ID>`**. The outer
prefix selects LiteLLM's OpenRouter adapter; the rest is the identifier from
[OpenRouter's catalog](https://openrouter.ai/models), such as
`openai/gpt-4.1-mini`, `anthropic/claude-sonnet-4`, or
`meta-llama/llama-3.3-70b-instruct`. Keep any catalog suffix, such as `:free`,
when selecting that particular variant. Availability and limits can change.

### Quick start

Install `ellements` normally and set an OpenRouter key:

```bash
export OPENROUTER_API_KEY="your-openrouter-api-key"
```

```python
import asyncio

from ellements.core import LLMClient


async def main() -> None:
    client = LLMClient(model="openrouter/openai/gpt-4.1-mini")
    answer = await client.complete(
        "Explain model checking in one paragraph.",
        max_tokens=300,
    )
    print(answer)


asyncio.run(main())
```

LiteLLM resolves the environment key and the default endpoint,
`https://openrouter.ai/api/v1`. You do not need an OpenAI or Anthropic key to
use their models through OpenRouter, and no OpenRouter SDK is installed.
Explicit provider prefixes are preserved, including
`openrouter/openai/gpt-5-mini`; `use_responses_api=True` does not redirect an
OpenRouter call to OpenAI or change its tool format.

### Credentials, headers, and routing preferences

Use the existing constructor options when configuration comes from your
application instead of provider environment defaults:

```python
import os

from ellements.core import LLMClient

client = LLMClient(
    model="openrouter/openai/gpt-4.1-mini",
    api_key=os.environ["OPENROUTER_API_KEY"],
    extra_headers={
        "HTTP-Referer": "https://example.com",
        "X-OpenRouter-Title": "My Ellements experiment",
    },
    extra_body={
        "provider": {
            "sort": "price",
            "require_parameters": True,
        },
    },
)
```

App-attribution headers are optional. `extra_body` carries OpenRouter-specific
options without introducing a parallel Ellements configuration API. In this
example, routing prefers lower prices and requires an upstream provider that
supports the requested parameters. See
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
for latency/throughput sorting, fallback controls, and data-policy constraints.

Constructor settings are **client-local** and forwarded on each request, not
written to LiteLLM's process-wide credentials or endpoint. Per-call options
override them; mapping-valued options such as `extra_body` and `extra_headers`
are replaced as a whole, not deep-merged. To override the endpoint, pass
`api_base="https://your-endpoint.example/api/v1"`; `base_url` is also accepted
and normalized to `api_base`. If both appear in the same configuration layer,
`api_base` takes precedence. Otherwise, let LiteLLM use the provider default or
`OPENROUTER_API_BASE`.

Direct-provider and OpenRouter clients can coexist in the same process. A
per-call `model=` override changes the route, not the client's explicit
credentials or endpoint, so use separate clients for different providers or
override those connection settings together.

### Existing capabilities stay composable

Use `complete`, `stream`, `complete_structured`, `complete_with_tools`, and
conversations as usual. Strategies and caching, rate-limiting, and budgeting
wrappers accept the same client; observer events and Ellements' centralized
retry policy remain in place.

Inside an async function, for example:

```python
from pydantic import BaseModel


class Summary(BaseModel):
    main_point: str


summary = await client.complete_structured("Summarize model checking.", Summary)

async for chunk in client.stream("Give a short example."):
    print(chunk, end="", flush=True)
```

OpenRouter is a route, not a promise that every model supports every feature.
Choose a model and upstream provider with support for your requested tools,
vision inputs, structured output, or log-probabilities. Structured output uses
LiteLLM's capability metadata and native schema requests; unsupported models
still raise `StructuredOutputUnsupportedError`, rather than falling back to
unconstrained JSON prompting. Image generation/editing likewise requires a
compatible model and LiteLLM adapter; those methods use the client's model
unless explicitly overridden.

### Why use it in practice?

- **Compare models with less setup.** Run the same prompt or strategy against
  several vendors using one OpenRouter account and billing surface.
- **Explore cost and speed.** Change the catalog model or provider preferences
  rather than rewriting application logic.
- **Improve availability.** OpenRouter can route among upstream providers and
  apply configured fallbacks. These are distinct from Ellements retrying a
  transient LiteLLM error.

This adds an intermediary, not a guarantee of lower cost or uninterrupted
service. Review current pricing, rate limits, model capabilities, and both
OpenRouter's and upstream providers' data policies before sending sensitive
inputs. See [LiteLLM's OpenRouter guide](https://docs.litellm.ai/docs/providers/openrouter)
for adapter-specific options.

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

### Governed completion transports

`LLMClient(model=..., completion_transport=transport)` routes **every actual
non-streaming completion attempt** through a `CompletionTransport`, below tool
iteration, structured parsing and retries. `complete(CompletionRequest)` returns
the raw provider `ModelResponse`. `CompletionRequest.as_json()` converts native
Pydantic response schemas using LiteLLM's strict-schema adapter and rejects
non-JSON Python objects. A transport can execute through an independently guarded
company boundary rather than the application's provider credentials.

Transport refusal is not telemetry: it propagates and there is no direct-provider
fallback. Each retry calls the transport again, allowing separate admission;
transports must not implement another retry loop. Native streaming is explicitly
unavailable when this transport is configured. Image generation has a separate
provider path and is not governed by a **completion** transport. High-level
`BudgetedLLMClient` trackers and fail-open logging observers are not substitutes
for financial admission/settlement at an actual provider boundary.

Add stable primitives here when more than one package should be able to reuse
them. Prefer a small protocol plus one obvious implementation; keep provider
wire formats behind dialects; and do not hide behavior in broad root exports.
# Receipt-preserving image generation

`LLMClient(..., image_generation_transport=OpenAIImageGenerationTransport(
timeout_seconds=900))` uses the official asynchronous image SDK and retains
observed provider request identities in `ImageGenerationResponse.provider_receipt_ids`.
Import the transport from `ellements.core.llm.image_transport`.
The transport accepts one explicit text-only image request, no hidden image
inputs, fixed OpenAI endpoint and no SDK retries. Use `max_retries=0` and no local
cache for externally accounted one-shot requests. Missing receipt identity is an
empty tuple, never a synthesized local identifier. Generation still uses the
shared client's observer pipeline. This primitive does not grant spending,
source-use, publication or organization authority.

`OpenAIImageGenerationTransport.preflight()` checks only that this process has
nonempty `OPENAI_API_KEY` credentials. Call it before financial reservation when
preparing a governed request. It does not discover credentials, source a shell,
authenticate remotely, or retain credential values. An SDK constructor/context-entry
failure before the request phase raises `ImageGenerationNotStartedError`; request,
timeout and response-parse failures still raise `ImageGenerationTransportError`
and remain uncertain. Both expose bounded failure facts without exception messages
or response bodies. Nonexecution evidence is not itself ledger-release or retry
authority; the owning guarded spending boundary must apply its disposition rules.
