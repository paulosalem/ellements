# ellements-execution

`ellements-execution` contributes `ellements.execution`: reusable prompting
strategies that orchestrate one or more LLM calls through `ellements.core`.
Strategies are not model clients. They are small execution patterns with typed
configs, explicit prompt keys, and step records that can be inspected later.

## Principles

- **One protocol.** A strategy is anything with `execute(prompts, client, tools,
  config) -> StrategyResult`.
- **Prompt keys are contracts.** Missing required prompts raise
  `PromptKeyMissingError`; there is no silent fallback.
- **Retries belong to the client.** Strategies sequence calls; `LLMClient`
  handles transient provider failures.
- **Structured decisions stay structured.** Reflection uses `CritiqueResult`;
  tree-of-thought evaluation uses `Evaluation(score, reasoning)`.
- **Steps are first-class.** Every strategy returns `StrategyResult(output,
  steps, metadata)`, and configs can receive `on_step` callbacks.
- **Human edits are callbacks.** Collaborative editing uses `EditCallback`, so
  terminal editors, tests, or future UIs can all drive the same loop.

## Structure

| Module | Role |
| --- | --- |
| `strategies.py` | `Strategy` protocol, `BaseStrategy`, `StepRecord`, `StrategyResult` |
| `config.py` | Shared and per-strategy Pydantic configs |
| `single_call.py` | One prompt, one completion |
| `self_consistency.py` | Sample N answers, aggregate by vote or LLM judge |
| `reflection.py` | Generate → structured critique → revise |
| `tree_of_thought.py` | Beam, DFS, or flat search with structured evaluation |
| `collaborative.py`, `callbacks.py` | LLM draft → human edit → LLM continuation |
| `catalog.py` | Built-in strategy registry grouped by family |

## Examples

```python
from ellements.execution import SingleCallStrategy

result = await SingleCallStrategy().execute(
    prompts={"default": "Explain experiment-oriented computing."},
    client=client,
)
print(result.output)
```

```python
from ellements.execution import ReflectionConfig, ReflectionStrategy

result = await ReflectionStrategy().execute(
    prompts={
        "generate": "Draft a concise project description.",
        "critique": "Return a CritiqueResult for this draft:\n\n{{response}}",
        "revise": "Revise the draft.\n\nDraft:\n{{response}}\n\nIssues:\n{{issues}}",
    },
    client=client,
    config=ReflectionConfig(max_rounds=2),
)
```

```python
from ellements.execution import SelfConsistencyConfig, SelfConsistencyStrategy

steps = []
result = await SelfConsistencyStrategy().execute(
    prompts={"default": "Solve the problem and return only the final answer."},
    client=client,
    config=SelfConsistencyConfig(samples=5, on_step=steps.append),
)
```

## Extending

New strategies should implement `Strategy`, define a dedicated `*Config`, state
their required prompt keys in code and documentation, emit meaningful
`StepRecord`s, and avoid their own retry layer. Runtime prompt templates support
Mustache placeholders such as `{{response}}` and PromptSpec-style placeholders
such as `@{response}`. Use structured Pydantic outputs whenever a decision must
be machine-readable.
