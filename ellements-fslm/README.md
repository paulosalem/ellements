# ellements-fslm

`ellements-fslm` contributes `ellements.fslm`: finite-state linguistic machines
for agentic workflows that need explicit control. A machine graph decides what is
possible; deterministic code handles crisp logic; natural-language evaluators
handle semantic judgment when crisp logic would be the wrong tool.

The name is intentionally **FSLM**, not just state machine terminology with a new
coat of paint. The linguistic part matters: guards, invariants, actions, and
outputs may be backed by prompts when semantic judgment is the point.

The command-line entry point is `fslm`. It emits JSON by default for automation,
and `--format rich` when a human wants to inspect transitions, guard decisions,
outputs, and trace context.

## Principles

- **Locus of control.** The current state declares legal events, tools, outputs,
  invariants, transitions, recovery paths, and budget overrides.
- **Deterministic first.** Use `ellements.fslm.det` for exact predicates,
  effects, and outputs; use `ellements.fslm.nl` only when the condition is
  semantic.
- **Actions are not effects.** Effects mutate the snapshot. Actions mutate the
  world through declared affordances.
- **Recovery is part of the graph.** Failure, low confidence, and blocked safety
  checks should route through explicit transitions.
- **Python is the semantic ground truth.** YAML is a useful graph/spec surface,
  but executable behavior resolves through Python bindings.
- **Every step is observable.** Kernels produce snapshots, decisions, outputs,
  action records, and observer events suitable for persistence or replay.

## Structure

| Module | Role |
| --- | --- |
| `models.py` | Pydantic specs, snapshots, events, decisions, outputs, step results |
| `dsl.py` | Fluent Python builder: `machine(...)`, states, transitions, guards |
| `det.py`, `nl.py` | Deterministic and natural-language helper namespaces |
| `definition.py`, `loading.py` | Executable definitions, runtime bindings, YAML/Python loading |
| `kernel.py` | Single-step transition kernel and evaluator/executor protocols |
| `evaluators.py` | LLM-backed guard, invariant, action, and output evaluation |
| `persistence.py`, `observers.py` | In-memory/local stores and JSONL/Rich observers |
| `visualization.py`, `rendering.py`, `cli.py` | Mermaid, Rich rendering, and `fslm` CLI |

## Examples

```python
from ellements.fslm import FSLMEvent, FSLMKernel, machine

m = machine("triage", initial="intake")
with m.state("intake") as s:
    s.on("ticket").to("resolved", "auto_resolve").when("obvious")
m.state("resolved", terminal=True)

definition = m.build()
snapshot = definition.initial_snapshot()

result = await FSLMKernel(definition).step(
    snapshot,
    FSLMEvent(type="ticket", payload={"guards": {"obvious": True}}),
)
print(result.new_snapshot.current_state)
```

```python
from ellements.fslm import FSLMEvent, FSLMKernel, det, machine


def has_approval(ctx) -> bool:
    return ctx.event.payload.get("approved") is True


m = machine("approval", initial="waiting")
with m.state("waiting") as s:
    s.on("submit").to("done", "accept").when(
        det.guard("has_approval", has_approval)
    )
m.state("done", terminal=True)
```

```bash
fslm validate machine.yaml
fslm mermaid machine.yaml > machine.mmd
fslm init-state machine.yaml --state-dir .fslm-state
fslm step machine.yaml --state-dir .fslm-state --event event.json
```

## PromptSpec integration

PromptSpec’s `@execute fslm` engine imports this package directly as
`ellements.fslm`. PromptSpec owns the prompt library; `ellements.fslm` owns the
machine graph and runtime contract. Natural-language guards conventionally map
to prompts such as `guard.<id>`, invariants to `invariant.<id>`, actions to
`action.<name>`, and outputs to `output.<type>`.

## Extending

Start with the graph. If a behavior cannot be described as a state, event,
transition, invariant, action, or output, it probably does not belong in the
kernel. Add reusable deterministic helpers to `det.py`, semantic helper specs to
`nl.py`, and backend-specific side effects through runtime bindings rather than
hidden callbacks.

See [`DESIGN.md`](DESIGN.md) for the longer design reference.
