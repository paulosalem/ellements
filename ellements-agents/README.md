# ellements-agents

`ellements-agents` contributes `ellements.agents`: a backend-agnostic layer over
external agent runtimes. OpenAI Agents and Claude Agents are adapters. The point
of this package is the seam above those libraries: builders, controllers,
events, progress reporting, stats, and tool adaptation.

## Principles

- **Backend protocol at the center.** `AgentBackend` is the single integration
  point for runtime-specific code.
- **Tools remain core tools.** Backends receive a `ToolRegistry` and adapt
  `ToolSpec`s to their native SDK format.
- **Controllers are presentation-free.** `AgentController` owns sessions,
  persona/guideline state, history, and stats without knowing about a UI.
- **Events are normalized.** Streaming backends emit `AgentEvent` so progress
  renderers and TUIs do not branch on provider internals.
- **Stats are explicit.** `AgentRunStats` records tool calls, outputs, observed
  items, and custom metrics without hidden aliases.

## Structure

| Module | Role |
| --- | --- |
| `backend.py` | `AgentBackend` and streaming handle protocols |
| `builder.py` | Fluent `AgentBuilder` for name, model, instructions, personas, guidelines, and tools |
| `controller.py` | Reusable controller base for stateful agent apps |
| `runner.py` | `run_agent_with_progress`, `AgentRunResult`, `AgentRunStats` |
| `openai_backend.py`, `claude_backend.py` | Concrete runtime adapters |
| `tools.py` | Helpers for adapting methods into tools |

## Examples

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

```python
from ellements.agents import run_agent_with_progress

result = await run_agent_with_progress(
    backend=backend,
    agent=agent,
    query="Find the main trade-offs.",
    progress_callback=print,
)

print(result.final_output)
print(result.stats.to_dict())
```

```python
from ellements.agents import AgentController, ControllerConfig
from ellements.core import ToolRegistry


class ResearchController(AgentController):
    def _build_agent(self):
        return self.backend.create_agent(
            name="researcher",
            instructions=self._get_fallback_instructions(),
            tools=ToolRegistry(),
            model=self.config.model,
        )

    def _get_fallback_instructions(self) -> str:
        return "Answer carefully and cite uncertainty."
```

## Extending

Add a backend by implementing `AgentBackend`: `create_agent`, `create_session`,
`run`, and `stream_run`. Keep SDK-specific translation inside the adapter; keep
tools as `ToolRegistry`; emit normalized `AgentEvent`s when streaming; and let
controllers or UI layers decide how progress is displayed.
