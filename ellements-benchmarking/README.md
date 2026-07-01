# ellements-benchmarking

`ellements-benchmarking` contributes `ellements.benchmarking`: adapters that let
`ellements.core.LLMClient` and `ellements.execution.Strategy` run through
`lm-evaluation-harness` tasks. It is meant for quick comparisons, not for
pretending benchmark numbers are more stable than the models that produced them.

## Principles

- **Use the standard harness.** This package wraps `lm-evaluation-harness`
  instead of inventing a benchmark format.
- **Preserve provider prefixes.** Model names such as `openai/gpt-4.1` are
  passed through unchanged so LiteLLM can route correctly.
- **One persistent event loop.** `BenchmarkModel` owns a background asyncio loop
  so sync lm-eval calls can drive async LLM calls safely.
- **Hard-fail missing logprobs.** Multiple-choice/loglikelihood tasks raise
  `LogprobsUnsupportedError` when the model cannot provide what the task needs.
- **Strategies affect generation only.** `Strategy.execute()` is used for
  generative tasks; loglikelihood remains an intrinsic model operation.

## Structure

| Module | Role |
| --- | --- |
| `harness.py` | `BenchmarkModel`, `run_benchmark`, `compare_benchmarks` |
| `results.py` | `BenchmarkComparison` formatting and JSON/CSV export |

## Examples

```python
from ellements.benchmarking import run_benchmark

results = run_benchmark(
    model="openai/gpt-4.1",
    tasks=["gsm8k"],
    limit=20,
)
```

```python
from ellements.benchmarking import compare_benchmarks, run_benchmark
from ellements.execution import SelfConsistencyConfig, SelfConsistencyStrategy

results = run_benchmark(
    model="openai/gpt-4.1",
    tasks=["gsm8k"],
    limit=20,
    strategy=SelfConsistencyStrategy(),
    strategy_config=SelfConsistencyConfig(samples=5),
)

comparison = compare_benchmarks(
    model="openai/gpt-4.1",
    tasks=["gsm8k"],
    limit=20,
    strategies={
        "direct": None,
        "self_consistency": SelfConsistencyStrategy(),
    },
)

comparison.print_table()
comparison.to_json("outputs/benchmark-comparison.json")
```

## Extending

Keep benchmark orchestration in `harness.py` and presentation/export helpers in
`results.py`. If a task needs behavior lm-eval does not expose cleanly, prefer a
thin adapter over a parallel benchmark framework. Surface unsupported model
capabilities explicitly; do not convert missing evidence into friendly zeros.
