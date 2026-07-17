# ellements.fslm design reference

This document is the source-of-truth design reference for `ellements.fslm`.
Update it whenever the public design or implementation semantics change.

`fslm` is the CLI command name only. The Python package remains
`ellements.fslm`.

## 1. Purpose

`ellements.fslm` provides finite-state linguistic machines: finite-state
machines whose legal behavior is constrained by an explicit graph, but whose
guards, invariants, outputs, and actions may use deterministic Python logic,
natural-language judgment, tools, coordination artifacts, and external systems.

The primary design goal is bounded autonomy:

- the machine graph decides what is possible;
- the current state defines the local locus of control;
- deterministic code handles crisp logic;
- natural-language evaluators handle semantic judgment;
- actions mutate the world only through declared affordances;
- every step can be observed, persisted, and replayed as far as its configured
  side-effect policy allows.

The first important use case is supervising AI coding agents such as Claude
Code or Copilot CLI, but the library must remain general enough for other
workflow, monitoring, validation, game, simulation, and coordination tasks.

## 2. Non-goals

`ellements.fslm` is not:

- a replacement for all workflow engines;
- a full statechart engine with nested, parallel, or orthogonal states;
- a general queue/scheduler/broker;
- an unbounded LLM agent framework;
- a YAML-only workflow language that can execute arbitrary behavior without
  Python-backed bindings;
- a hidden callback machine where arbitrary code executes implicitly.

The v1 design is deliberately flat, explicit, Python-backed, async-first, and
small.

## 3. Core principles

### 3.1 Locus of control

The current state is the primary locus of control. A state declares what the
machine may observe, decide, emit, and do while it is active:

- allowed event types;
- local objective;
- state-local tools/actions;
- permitted outputs;
- invariants;
- normal transitions;
- recovery transitions;
- optional state budget overrides.

Global policy may restrict, interrupt, log, require approval, or cap behavior.
It must not silently expand a state's affordances. If global policy needs a
special path such as cancellation, budget exhaustion, or approval, that path
should be modeled as explicit machine-level events and transitions.

### 3.2 Python-backed definition surfaces

Machine definitions may be authored either in Python or in YAML. Python is the
semantic ground truth: whenever a machine needs deterministic predicates,
side-effectful calls, custom tools, custom evaluators, or rich runtime behavior,
those pieces are Python objects referenced by the machine definition.

YAML is accepted as a declarative graph/spec surface, not as a programming
language. Wherever YAML needs executable behavior, it uses stable binding
identifiers that resolve to:

- built-in ellements.fslm functions;
- caller-supplied runtime bindings;
- functions/classes in explicitly imported companion Python modules;
- reusable "family" modules maintained by users or applications.

This makes YAML useful for lightweight configuration and future generated
machines while keeping behavior explicit, testable, and Python-backed.

JSON remains useful for:

- serialized `MachineSpec` artifacts;
- YAML-to-spec compilation outputs;
- snapshots;
- events;
- step results;
- traces;
- debugging and interchange between tools.

Executable behavior always resolves through Python bindings.

### 3.3 Deterministic first, natural language where needed

Use deterministic logic whenever a condition or action is crisp:

- exact JSON-path checks;
- variable comparisons;
- arithmetic;
- process exit code checks;
- registered Python predicates;
- direct Python side-effect calls;
- exact tool arguments.

Use natural-language evaluators when the machine needs semantic judgment:

- interpreting messy CLI output;
- assessing whether a plan is actionable;
- checking whether edits match scope;
- synthesizing a user-facing output;
- choosing tool arguments from ambiguous context;
- suggesting recovery among declared options.

### 3.4 Actions are not effects

Effects mutate the machine snapshot. Actions mutate the world.

```text
effects -> pure variable/snapshot updates
actions -> tool calls, Python side effects, coordination posts, terminal runs
```

This distinction keeps replayability and observability understandable.

### 3.5 Explicit recovery

Recovery is part of the graph, not a hidden fallback. Failures, low confidence,
blocked safety checks, approval requirements, and validation errors should route
through explicit recovery transitions or explicit generated events that can
trigger those transitions.

### 3.6 Async-first

The runtime is async-first because ellements LLM clients, coordination spaces,
streaming processes, and tool execution are async-shaped. Sync callables may be
accepted ergonomically, but the runtime normalizes them into async execution.

## 4. Package shape

Public package:

```text
ellements.fslm
```

CLI command:

```text
fslm
```

Expected module areas:

```text
ellements.fslm
  models.py          # canonical pydantic models
  dsl.py             # fluent Python DSL
  det.py             # deterministic helper namespace
  nl.py              # natural-language helper namespace
  context.py         # FSLMContext
  kernel.py          # single-step deterministic kernel
  runner.py          # loops, queues, budgets, stores, tool wiring
  actions.py         # action planning/execution records and executors
  evaluators.py      # guard/invariant/output/action evaluator protocols
  loading.py         # Python/YAML loading and binding resolution
  persistence.py     # memory/local stores
  observers.py       # FSLM observer events
  visualization.py   # Mermaid rendering
  coordination.py    # optional ellements.coordination adapter
  cli.py             # fslm command
```

Some modules may remain small or be collapsed during implementation, but the
conceptual boundaries should stay clear.

## 5. Definition model

There are two related concepts:

### 5.1 `MachineSpec`

`MachineSpec` is the structural, mostly serializable description of the
machine:

- states;
- transitions;
- event patterns;
- natural-language prompt text;
- tool references;
- output schemas;
- policy;
- budgets;
- binding references;
- metadata.

It should be Pydantic-based and JSON-serializable whenever possible.

Serializable specs may contain references such as `guards.files_changed` or
`builtin.payload_equals`; they do not contain the Python callable itself.

### 5.2 `MachineDefinition`

`MachineDefinition` is the executable Python definition:

```python
MachineDefinition(
    spec=MachineSpec(...),
    bindings=RuntimeBindings(...),
)
```

Bindings hold non-serializable runtime objects:

- deterministic guard callables;
- deterministic invariant callables;
- deterministic output callables;
- deterministic effect callables;
- side-effectful Python action callables;
- tool registries;
- custom evaluators;
- context factories;
- dependency objects.

The fluent DSL and YAML loader may hide this split ergonomically, but the
runtime must preserve it. A JSON/YAML `MachineSpec` can be inspected or
visualized without resolving bindings, but Python bindings are needed to execute
deterministic callables and side-effectful actions.

For compatibility and convenience, APIs may accept:

```python
MachineSpec | MachineDefinition | MachineBuilder
```

and normalize internally.

### 5.3 Binding references

Binding references are stable names in serializable specs that resolve to
Python objects at load/runtime:

```yaml
guards:
  - id: files_changed
    kind: deterministic
    ref: guards.files_changed
```

The resolved object may be a predicate, invariant, output builder, effect
builder, action callable, tool factory, evaluator, store, or observer.

Reference forms:

| Form | Meaning |
| --- | --- |
| `builtin.name` | Built-in ellements.fslm helper |
| `alias.name` | Object in an imported binding module alias |
| `package.module:object` | Direct import path |
| `package.module.object` | Optional dotted import path if unambiguous |

Resolution order should be deterministic:

1. explicit runtime binding registry;
2. YAML-declared import aliases;
3. built-in registry;
4. direct import path.

Unresolved references are spec/load errors, not runtime surprises.

## 6. Loading machine definitions

`fslm` loads machine definitions by reference:

```text
path/to/machine.py
path/to/machine.py:export_name
package.module:export_name
path/to/machine.yaml
path/to/machine.yaml --bindings path/to/bindings.py
```

Python module default export names:

```text
spec
machine_spec
definition
machine_definition
build
machine
```

An export may be:

- a `MachineDefinition`;
- a `MachineSpec`;
- a fluent builder with `.build()`;
- a callable returning any of the above.

If the export is only a `MachineSpec`, execution is limited to serializable
behavior plus externally supplied bindings.

YAML specs are loaded as declarative `MachineSpec` data plus binding references.
They may declare companion binding modules directly:

```yaml
bindings:
  imports:
    guards: ./supervisor_guards.py
    actions: ./supervisor_actions.py
    common: my_project.fsm_common
```

CLI/runtime callers may also supply bindings externally:

```bash
fslm validate supervisor.yaml --bindings supervisor_bindings.py
fslm step supervisor.yaml --bindings family.py --snapshot snapshot.json --event event.json
```

YAML loading has two phases:

1. Parse and validate the structural spec.
2. Resolve binding references against built-ins, declared imports, and
   externally supplied runtime bindings.

Structural operations such as `fslm mermaid` may work without resolving every
binding. Execution must resolve all binding references needed by the active
path.

## 7. External plugin modules

Machine files should be allowed to stay short and readable by importing reusable
logic from ordinary Python modules. YAML specs should use the same plugin modules
through binding references.

This is the recommended pattern for non-trivial machines:

```text
my_project/
  machines/
    supervisor.py       # mostly state/transition structure
  fsm_plugins/
    guards.py           # deterministic predicates
    invariants.py       # deterministic invariants
    actions.py          # side-effectful calls and deterministic tool args
    outputs.py          # deterministic output builders
    effects.py          # pure snapshot variable patches
    evaluators.py       # custom NL evaluator implementations
    tools.py            # ToolRegistry / ToolSpec factories
    stores.py           # custom persistence stores
    events.py           # event interpreters/adapters
```

Example:

```python
# machines/supervisor.py
from ellements.fslm import det, machine, nl
from my_project.fsm_plugins.guards import files_changed, validation_passed
from my_project.fsm_plugins.actions import write_marker_file
from my_project.fsm_plugins.outputs import validation_result

m = machine("supervisor", initial="implementing")

with m.state("implementing", tools=["terminal.run"]) as s:
    s.on("implementation_complete").to("verifying", "start_validation").when(
        det.guard("files_changed", files_changed),
    ).call(
        write_marker_file,
        name="write_marker_file",
    )

with m.state("verifying") as s:
    s.on("terminal_result").to("reporting", "validation_passed").when(
        det.guard("validation_passed", validation_passed),
    ).emit(
        det.output("ValidationResult", validation_result),
    )

definition = m.build()
```

External functions are just Python callables receiving `FSLMContext`.

Benefits:

- machine files remain architectural and readable;
- deterministic logic can be unit-tested independently;
- side-effectful integrations stay isolated;
- functions can be reused across machines;
- application dependencies do not leak into the core FSLM package.

Recommended plugin boundaries:

| Plugin piece | Purpose | Typical return |
| --- | --- | --- |
| guard functions | crisp transition checks | `bool` or `DecisionResult` |
| invariant functions | crisp state validity checks | `bool` or `DecisionResult` |
| effect functions | pure snapshot variable patches | `dict` or patch object |
| action functions | trusted side effects | `dict` or `ActionResult` |
| output functions | typed deterministic outputs | payload `dict` or `OutputRecord` |
| event adapters | convert external observations into events | `FSLMEvent` |
| tool factories | provide reusable ellements tools | `ToolRegistry` / `ToolSpec` |
| evaluator classes | custom NL or hybrid judgment | protocol implementations |
| store factories | custom persistence | runtime store implementation |
| observers | logs, console, metrics | `FSLMObserver` |

The FSLM module should never require these pieces to live next to the machine
definition. Importing them is enough.

## 8. YAML specs with Python bindings

YAML is a declarative authoring format for the graph, natural-language text,
policy, and references to executable pieces. It is useful for:

- simple machines that mostly use built-in predicates/effects/actions;
- machine families that share a binding module;
- generated machines;
- WeaveMark-to-FSLM compilation.

YAML should not attempt to embed Python code. Executable behavior is referenced.

Example:

```yaml
name: copilot-session-supervisor
initial: planning

bindings:
  imports:
    guards: ./supervisor_guards.py
    outputs: ./supervisor_outputs.py
    actions: ./supervisor_actions.py
    family: my_project.fsm_families.coding_session

policy:
  execution: execute
  traces: jsonl
  terminal_safety: nl

states:
  planning:
    objective: |
      Understand the request and produce a scoped implementation plan.
      No repository edits are allowed here.
    tools: [repo.search, repo.read]
    emits: [PlanDraft, NeedClarification]
    invariants:
      - id: no_files_modified
        kind: deterministic
        ref: guards.no_files_modified
    transitions:
      - name: accept_plan
        event: plan_candidate
        target: implementing
        guards:
          - id: plan_is_actionable
            kind: nl
            text: |
              The plan identifies behavior change, likely files, validation,
              and remaining uncertainty.
          - id: not_paused
            kind: deterministic
            ref: guards.not_paused
        emits:
          - type: PlanDraft
            kind: deterministic
            ref: outputs.plan_draft_payload

  implementing:
    tools: [repo.edit, terminal.run]
    transitions:
      - name: apply_edit
        event: edit_required
        target: implementing
        actions:
          - name: edit_scoped_files
            kind: nl
            tool: repo.edit
            text: |
              Make the smallest file edit that advances the accepted plan.
      - name: start_validation
        event: implementation_complete
        target: verifying
        guards:
          - id: files_changed
            kind: deterministic
            ref: family.files_changed
        actions:
          - name: write_marker_file
            kind: deterministic
            ref: actions.write_marker_file
```

### 8.1 Built-in references

The library should provide a small standard library of YAML-friendly built-ins,
for common deterministic cases:

```yaml
guards:
  - id: exit_code_zero
    kind: deterministic
    ref: builtin.payload_equals
    args:
      path: $.event.payload.exit_code
      value: 0

effects:
  - ref: builtin.assign
    args:
      path: $.snapshot.variables.validation_attempted
      value: true
```

Initial useful built-ins:

- `builtin.payload_exists`
- `builtin.payload_equals`
- `builtin.payload_not_equals`
- `builtin.var_exists`
- `builtin.var_equals`
- `builtin.var_not_equals`
- `builtin.assign`
- `builtin.increment`
- `builtin.append`
- `builtin.copy_payload_to_var`

Built-ins should be small, explicit, and easy to reimplement by users.

### 8.2 Companion modules and FSLM families

Users can create families of machines by defining a shared binding module:

```python
# coding_session_family.py
def files_changed(ctx): ...
def validation_passed(ctx): ...
def no_files_modified(ctx): ...
def plan_draft_payload(ctx): ...
def write_marker_file(ctx): ...
```

Then many YAML files can reuse it:

```yaml
bindings:
  imports:
    family: ./coding_session_family.py
```

This allows a domain expert to define the Python extension points once, then
author many concise YAML machines in the same family.

### 8.3 WeaveMark integration

WeaveMark compiles inline machine sugar to:

- a YAML machine spec;
- references to built-in bindings;
- references to a standard generated or user-supplied companion module;
- optional generated Python bindings when semantic behavior cannot be expressed
  through built-ins.

The key idea is that WeaveMark should not need to generate arbitrary opaque
runtime behavior when a standard binding family already exists.

## 9. Fluent DSL

The default authoring style is fluent and state-local:

```python
from ellements.fslm import det, machine, nl
from ellements.standard_tools import terminal_cli_tool

m = machine(
    "copilot-session-supervisor",
    initial="planning",
    description="""
    Supervises an AI coding session. The current state is always the locus of
    control.
    """,
)

m.policy(
    execution="execute",
    traces="jsonl",
    verbose=True,
    terminal_safety="nl",
)

m.use_tools(
    terminal_cli_tool(name="terminal.run", timeout_seconds=300),
)

with m.state(
    "planning",
    objective="""
    Understand the request and produce a scoped implementation plan.
    No repository edits are allowed here.
    """,
    tools=["repo.search", "repo.read"],
    emits=["PlanDraft", "NeedClarification"],
) as s:
    s.invariant(
        det.invariant(
            "no_files_modified",
            lambda ctx: ctx.vars.get("modified_files", []) == [],
        )
    )

    s.on("plan_candidate").to("implementing", "accept_plan").when(
        nl.guard(
            "plan_is_actionable",
            """
            The plan identifies the intended behavior change, likely files,
            validation approach, and remaining uncertainty.
            """,
        ),
        det.guard(
            "not_paused",
            lambda ctx: not ctx.vars.get("pause_requested", False),
        ),
    ).emit(
        nl.output(
            "PlanDraft",
            """
            Summarize the accepted implementation plan with scope, likely files,
            and validation strategy.
            """,
        )
    )

with m.state("implementing", tools=["repo.edit", "terminal.run"]) as s:
    s.on("edit_required").stay("apply_edit").do(
        nl.action(
            "repo.edit",
            """
            Make the smallest file edit that advances the accepted plan.
            """,
        )
    )

    s.on("implementation_complete").to("verifying", "start_validation").when(
        det.guard("files_changed", lambda ctx: bool(ctx.vars.get("modified_files"))),
        nl.guard("validation_path_exists", "There is a concrete validation path."),
    )

definition = m.build()
```

Important ergonomic rules:

- `with m.state(...) as s:` keeps authority local and visible.
- one-line state declarations are valid for simple machines.
- common transition forms should have short, unsurprising shorthands.
- `.to("state", "transition_name")` declares a normal transition.
- `.stay("transition_name")` declares an explicit self-transition.
- `.recover(...)` declares explicit recovery transitions.
- `.when(...)` accepts deterministic and natural-language guards.
- `.do(...)` accepts deterministic, natural-language, or tool actions.
- `.emit(...)` accepts deterministic or natural-language outputs.
- `.effects(...)` is reserved for snapshot updates.
- `.call(...)` is shorthand for side-effectful Python action calls.

## 10. Progressive ergonomics

The library must support complex agentic machines without making simple
machines verbose. This should be achieved through progressive disclosure:
simple APIs are shorthands for the same canonical semantics, not separate
semantics.

### 10.1 Minimal deterministic machine

A very small FSLM should fit in a few lines:

```python
from ellements.fslm import machine

m = machine("turnstile", initial="locked")
m.state("locked").on("coin").to("unlocked")
m.state("unlocked").on("push").to("locked")

definition = m.build()
```

This expands naturally to named transitions:

```python
m.state("locked").on("coin").to("unlocked", "unlock")
```

If no transition name is provided, the builder should generate a stable,
readable name such as `locked_coin_to_unlocked`.

### 10.2 Compact self-transitions

Self-transitions should stay explicit but concise:

```python
m.state("polling").on("tick").stay("poll_again")
```

or, when the event name is sufficient:

```python
m.state("polling").on("tick").stay()
```

### 10.3 Inline guards and effects

Short deterministic logic should be easy:

```python
with m.state("checking") as s:
    s.on("result").to("done").when(lambda ctx: ctx.event.payload["ok"])
    s.on("result").stay().effects(attempted=True)
```

Inline lambdas are acceptable for small local predicates. Larger or reused
logic should be imported from plugin modules and wrapped with `det.guard(...)`
for naming and testability.

### 10.4 String shorthands

The DSL should accept useful shorthand forms:

```python
s.on("done").to("reporting")
s.on("retry").stay()
s.on("failed").to("blocked").emit("Failure")
s.invariant("has_owner")
s.on("ready").to("next").when("approved")
```

These map to deterministic IDs and default specs. They are appropriate for
structural sketches, tests, and machines where the runtime supplies a named
predicate registry.

### 10.5 Simple outputs and terminal states

Terminal and output declarations should not require ceremony:

```python
m.state("done", terminal=True)

with m.state("reporting") as s:
    s.on("ready").to("done").emit("FinalReport")
```

### 10.6 Simple Python module loading

The smallest loadable machine file should be straightforward:

```python
# turnstile.py
from ellements.fslm import machine

m = machine("turnstile", initial="locked")
m.state("locked").on("coin").to("unlocked")
m.state("unlocked").on("push").to("locked")

machine = m
```

Then:

```bash
fslm mermaid turnstile.py
```

### 10.7 Simple YAML loading

Simple YAML machines should also be concise when built-ins are enough:

```yaml
name: turnstile
initial: locked
states:
  locked:
    transitions:
      - event: coin
        target: unlocked
  unlocked:
    transitions:
      - event: push
        target: locked
```

More advanced YAML machines can stay readable by importing one family binding
module and using short references:

```yaml
bindings:
  imports:
    family: ./turnstile_family.py
```

### 10.8 No semantic fork

All shorthands must compile into the same underlying model as verbose forms.
There should not be a "simple machine" runtime and an "advanced machine"
runtime, nor a separate "YAML runtime". The simple path is just a pleasant way
to construct the same `MachineDefinition` / `MachineSpec`.

## 11. Canonical model vocabulary

### 11.1 `StateSpec`

A state declares the local locus of control:

- `name`;
- `objective`;
- `description`;
- `tools`;
- `affordances`;
- `allowed_event_types`;
- `emits`;
- `invariants`;
- `transitions`;
- `recovery_transitions`;
- `budgets`;
- `terminal`;
- `metadata`.

### 11.2 `TransitionSpec`

A transition declares one legal state step:

- `name`;
- `source`;
- `target`;
- `event`;
- `description`;
- `guards`;
- `actions`;
- `emits`;
- `effects`;
- `kind`: `normal` or `recovery`;
- `weight` / `random_group`;
- `metadata`.

### 11.3 `MachineSnapshot`

A snapshot is durable runtime state:

- machine identity;
- machine/spec version/hash;
- current state;
- variables;
- step index;
- pending actions;
- pending approvals;
- RNG seed/state;
- event cursor;
- metadata.

Snapshots should be small enough to persist often.

### 11.4 `FSLMEvent`

An event is a typed input fact:

- id;
- type;
- source;
- payload;
- timestamp;
- parent ids;
- confidence/evidence if interpreted;
- metadata.

Events may come from:

- user calls;
- terminal output;
- tool results;
- coordination artifacts;
- timers;
- file watchers;
- generated internal events.

### 11.5 `StepResult`

A step result records what happened:

- step id;
- input event id;
- source state;
- target state;
- status;
- selected transition;
- guard results;
- invariant results;
- actions;
- outputs;
- violations;
- random-choice record;
- trace summary;
- new snapshot.

## 12. `FSLMContext`

`FSLMContext` is the object passed to deterministic and natural-language
evaluation hooks.

Name matters: `fslm` is only the CLI command; the runtime context is
`FSLMContext`.

Suggested shape:

```python
@dataclass(slots=True)
class FSLMContext:
    spec: MachineSpec
    definition: MachineDefinition
    state: StateSpec
    transition: TransitionSpec | None
    snapshot: MachineSnapshot
    event: FSLMEvent
    vars: Mapping[str, Any]
    tools: ToolRegistry
    stores: RuntimeStores
    step_id: str
    run_id: str | None
    metadata: Mapping[str, Any]

    async def emit(self, output: OutputRecord | dict[str, Any]) -> None: ...
    async def signal(self, event: FSLMEvent | dict[str, Any]) -> None: ...
    async def call_tool(self, name: str, **arguments: Any) -> Any: ...
```

Design rules:

- `ctx.vars` should be treated as read-only by guards, invariants, actions, and
  outputs.
- Snapshot mutation should happen through deterministic effects, not arbitrary
  mutation of `ctx.vars`.
- Side-effectful actions may read context and mutate the world, but their
  results are recorded as action results.
- `ctx.emit(...)` creates typed outputs during advanced hooks.
- `ctx.signal(...)` creates internal or external events such as approval
  requests, safety failures, or action-failed signals.

## 13. Deterministic helper namespace: `det`

`det` is for exact Python logic and side-effectful Python actions.

### 13.1 Deterministic guards

```python
det.guard("exit_code_zero", lambda ctx: ctx.event.payload.get("exit_code") == 0)
```

The callable may be defined inline or imported from any other Python module:

```python
from my_project.fsm_plugins.guards import exit_code_zero

s.on("terminal_result").to("reporting", "validation_passed").when(
    det.guard("exit_code_zero", exit_code_zero),
)
```

Return forms:

- `bool`;
- `DecisionResult`;
- awaitable of either.

### 13.2 Deterministic invariants

```python
det.invariant(
    "validation_attempted",
    lambda ctx: ctx.vars.get("validation_attempted", False),
)
```

Return forms are the same as guards.

### 13.3 Deterministic outputs

```python
det.output(
    "ValidationResult",
    lambda ctx: {
        "passed": True,
        "command": ctx.event.payload.get("command_line"),
    },
)
```

Return forms:

- payload dict;
- `OutputRecord`;
- awaitable of either.

### 13.4 Pure deterministic effects

Effects update the snapshot variables:

```python
s.on("validation_needed").stay("run_validation").effects(
    validation_attempted=True,
    attempts=det.increment("attempts"),
)
```

Callable effects are also allowed:

```python
s.on("retry").stay("retrying").effect(
    det.effect(lambda ctx: {"retry_count": ctx.vars.get("retry_count", 0) + 1})
)
```

Return forms:

- dict patch;
- structured patch operations;
- awaitable of either.

Effects must be pure with respect to the outside world.

### 13.5 Deterministic tool actions

```python
det.action(
    "terminal.run",
    arguments=lambda ctx: {
        "command": "python",
        "args": ["-m", "pytest", "tests/test_feature.py", "-q"],
    },
    requires_safety_check=True,
)
```

This executes a declared tool with deterministic arguments.

### 13.6 Side-effectful Python calls

Direct Python side effects are allowed as explicit actions:

```python
def write_marker_file(ctx: FSLMContext) -> dict[str, Any]:
    path = Path(".fslm/marker.txt")
    path.write_text(f"state={ctx.snapshot.current_state}\n", encoding="utf-8")
    return {"path": str(path)}

s.on("implementation_complete").to("verifying", "start_validation").call(
    write_marker_file,
    name="write_marker_file",
)
```

Equivalent explicit form:

```python
s.on("implementation_complete").to("verifying", "start_validation").do(
    det.call("write_marker_file", write_marker_file)
)
```

Side-effectful calls:

- are trusted Python code;
- are not terminal-safety checked;
- should be recorded in `StepResult.actions`;
- should optionally declare idempotency metadata;
- should not be confused with pure effects.

## 14. Natural-language helper namespace: `nl`

`nl` is for semantic judgment and synthesis.

It is intentionally not called `llm`; LLMs are one implementation. Other
natural-language-capable evaluators may satisfy the same contracts.

### 14.1 NL guards

```python
nl.guard(
    "plan_is_actionable",
    """
    The plan identifies the behavior change, likely files, validation approach,
    and remaining uncertainty.
    """,
)
```

### 14.2 NL invariants

```python
nl.invariant(
    "edits_match_scope",
    """
    Every modified file and behavior change must be directly related to the
    accepted plan.
    """,
)
```

### 14.3 NL actions

```python
nl.action(
    "terminal.run",
    """
    Choose the narrowest existing validation command that gives useful
    confidence for the changed files.
    """,
    requires_safety_check=True,
)
```

The evaluator produces tool arguments, not arbitrary actions. It may only plan
within the tool/action affordance declared by the current state and transition.

### 14.4 NL outputs

```python
nl.output(
    "FailureAnalysis",
    """
    Explain the validation failure, likely cause, and direct repair path.
    """,
)
```

## 15. Structured decision records

Natural-language and deterministic evaluators normalize into structured
records:

```json
{
  "id": "plan_is_actionable",
  "allowed": true,
  "confidence": 0.87,
  "evidence": ["plan lists files", "plan names pytest validation"],
  "uncertainties": ["exact test path not yet confirmed"],
  "alternatives": ["remain_in_planning"]
}
```

Confidence is not proof. It is policy input.

Confidence policy should decide:

- proceed;
- deny guard;
- request approval;
- remain in state;
- emit ambiguity output;
- trigger recovery;
- block.

## 16. Step semantics

One call to `step(snapshot, event)` performs at most one transition.

Sequence:

1. Build `FSLMContext`.
2. Identify candidate transitions from the current state whose event pattern
   matches the event.
3. Evaluate guards.
4. Filter illegal transitions.
5. Select one legal transition:
   - deterministic priority/order by default;
   - weighted random selection when weights are declared.
6. Compute pure effects.
7. Plan/execute declared actions according to execution policy.
8. If required actions fail and policy does not allow continuation, block before
   committing the target snapshot.
9. Commit target snapshot and pure effects.
10. Check target-state invariants.
11. Produce outputs.
12. Persist/emit observer events as configured.
13. Return `StepResult`.

Self-transitions are ordinary transitions where `source == target`.

If no transition applies, return `StepResult(status="no_transition")`.

## 17. Action semantics

Actions are external side effects and are represented separately from effects.

Action types:

- deterministic tool action;
- NL-planned tool action;
- deterministic Python side-effect call;
- coordination artifact post;
- approval request;
- terminal command.

Ordering:

- actions run sequentially by default;
- later parallel action groups may be added explicitly;
- sequential default keeps error handling and replay understandable.

Execution policy:

- main mode executes actions;
- dry-run mode plans actions but does not execute them;
- approval requirements convert actions into pending approval records/signals;
- terminal actions pass through terminal safety unless disabled.

Return forms:

- dict payload;
- `ActionResult`;
- awaitable of either.

## 18. Terminal actions and safety

The reusable terminal tool lives outside the FSLM kernel, under ellements
standard tools.

Terminal safety:

- default-on per machine;
- disable per machine with policy when the caller intentionally trusts commands;
- implemented as a dedicated natural-language safety evaluator;
- evaluates command, args/script, cwd, env, intent, and state affordance;
- unsafe or uncertain checks do not execute the command;
- instead they emit a structured safety signal/event/output.

Terminal safety protects terminal actions only. It does not sandbox arbitrary
Python side-effect calls; those are trusted code.

## 19. Recovery semantics

Recovery transitions are explicit:

```python
s.recover("terminal_safety_failed").to(
    "waiting_for_approval",
    "request_terminal_approval",
)
```

Failure sources that may emit recovery events:

- guard evaluator exception;
- invariant violation;
- action failure;
- terminal safety blocked;
- approval denied;
- budget exhausted;
- low confidence;
- no transition when one was expected.

Core `step(...)` should not invent recovery paths. It may emit or return
structured error/signal records. A runner may enqueue those signals as events,
which then trigger declared recovery transitions.

## 20. Failure semantics

Failures should be structured and visible.

Default behavior:

- spec validation errors raise immediately;
- guard/invariant evaluator errors deny the decision and record an error unless
  policy says to raise;
- action errors stop remaining actions and block the step unless
  `continue_on_error` is configured;
- failed required actions prevent committing a non-self target snapshot;
- output production errors block or emit an output error according to policy;
- all runtime failures can generate internal events for explicit recovery.

The design should avoid broad silent fallbacks.

## 21. Probabilistic transitions

FSLM supports truly random choices where declared.

Example:

```python
s.on("coin_flip").choose(
    (0.8, "favorable", "go_favorable"),
    (0.2, "unfavorable", "go_unfavorable"),
)
```

Rules:

- random choice happens only among legal transitions after event and guard
  filtering;
- weights are normalized over surviving candidates;
- RNG seed/state is stored in the snapshot;
- the draw, candidate weights, and selected transition are recorded in the trace;
- replay can use the recorded sample or the seed/draw index.

## 22. Runner semantics

The kernel performs one step. Runners provide loops and integration.

### 22.1 `FSLMKernel.step(...)`

Single event, single snapshot, at most one transition.

### 22.2 `FSLMRunner.run_until(...)`

Convenience loop:

- reads events from a queue/source;
- calls `step(...)`;
- persists results;
- enqueues internal events;
- stops on terminal, blocked, waiting for approval, budget exhausted, or
  external cancellation.

### 22.3 Agentic runner

Adds active behavior:

- observes external systems;
- asks evaluators to interpret observations;
- plans actions;
- executes tools;
- monitors results;
- generates internal events;
- uses explicit recovery transitions.

The agentic runner is still constrained by current-state affordances.

## 23. Event queue semantics

Agentic operation needs an event queue.

Default:

- FIFO;
- external events and internal events both visible in traces;
- internal events record their parent step/action;
- queue depth is budgeted;
- one machine instance processes one event at a time;
- concurrent machine instances require coordination/CAS.

## 24. Persistence

Lightweight cases may run entirely in memory.

Local file layout:

```text
.fslm/
  snapshot.json
  events.jsonl
  results.jsonl
  traces.jsonl
```

Persistence is optional and configurable:

- no persistence;
- snapshot only;
- snapshot + events/results;
- full traces.

Full traces are useful for debugging and audit but should not be required for
light machines.

## 25. Observability

Keep FSLM events and LLM events separate but correlatable.

### 25.1 LLM events

Existing ellements `LLMObserver` events:

- request;
- response;
- error.

These are per model call.

### 25.2 FSLM events

FSLM observer events are machine-level:

- machine started/stopped;
- snapshot loaded/saved;
- event received/interpreted;
- transition considered/selected;
- guard evaluated;
- invariant checked/violated;
- action planned/executed/failed;
- terminal safety checked/blocked;
- output emitted;
- recovery triggered;
- approval requested;
- budget exhausted;
- step completed.

Correlate with:

- machine id;
- run id;
- step id;
- snapshot id/version;
- event id;
- LLM call ids when applicable.

Verbose console mode is a built-in FSLM observer, preferably using Rich.

## 26. Coordination integration

`ellements.coordination` integration is optional and bidirectional.

Receive artifacts as:

- events;
- approvals;
- external observations;
- action results;
- interrupts.

Emit artifacts as:

- snapshots;
- step results;
- traces;
- outputs;
- violations;
- action requests;
- action results;
- terminal safety blocked signals;
- approval requests.

Distributed state updates should use coordination CAS/version semantics to
avoid concurrent snapshot corruption.

## 27. CLI: `fslm`

The CLI operates on machine references, which may point to Python definitions,
YAML specs, or serialized JSON specs. YAML execution needs resolvable bindings.

Initial commands:

```text
fslm validate MACHINE_REF
fslm mermaid MACHINE_REF
fslm init-state MACHINE_REF
fslm inspect SNAPSHOT_JSON
fslm step MACHINE_REF --snapshot SNAPSHOT_JSON --event EVENT_JSON
fslm run MACHINE_REF
```

Useful options:

```text
--format json|rich
--color auto|always|never
--output PATH
--state-dir .fslm
--verbose
--dry-run
--seed N
--disable-terminal-safety
--bindings PATH_OR_MODULE
```

The CLI should not become a separate runtime. It should be a thin wrapper over
`ellements.fslm`.

## 28. WeaveMark integration

WeaveMark integrates at the adapter boundary; the `ellements.fslm` core models
and deterministic kernel remain independent of WeaveMark-specific assumptions.

WeaveMark may emit a YAML machine spec plus
binding references to built-in or user-supplied family modules. If the machine
requires custom executable behavior that cannot be represented through existing
bindings, WeaveMark may also emit a companion Python module.

WeaveMark may emit:

- YAML machine specs;
- companion Python binding modules;
- evaluator prompts;
- output schemas;
- tool declarations;
- example events;
- Mermaid diagrams.

The WeaveMark `@execute fslm` mode loads and runs generated artifacts
through the same `ellements.fslm` APIs used by the `fslm` CLI.

## 29. Security and trust model

Trust levels:

- `nl` evaluator output is untrusted judgment and must be constrained by specs.
- terminal commands are potentially dangerous and are safety-checked by default.
- Python side-effect calls are trusted code supplied by the machine author.
- coordination artifacts are external input and should be validated as events.
- tool outputs are external observations and should not bypass guards or
  invariants.

No hidden privilege escalation:

- a state cannot call tools outside its affordances;
- an NL evaluator cannot invent undeclared transitions;
- an action cannot execute without being declared;
- global policy can restrict or interrupt but not expand state-local power.

## 30. Testing strategy

Core tests:

- spec validation;
- fluent DSL building;
- Python module loading;
- YAML structural loading;
- YAML binding resolution;
- no transition;
- normal transition;
- self-transition;
- recovery transition;
- deterministic guards/invariants/effects;
- NL evaluator fixture outputs;
- action planning/execution;
- side-effectful Python action recording;
- invariant violations;
- seeded probabilistic selection;
- persistence;
- observers;
- CLI commands.

Integration tests:

- terminal tool safe path;
- terminal safety blocked path with fake evaluator;
- coordination artifact input/output;
- agentic event queue and recovery loop;
- WeaveMark-generated inline and external machine artifacts.

## 31. Ergonomic guidelines

APIs should read like a local contract:

```python
with m.state("verifying", tools=["terminal.run"]) as s:
    s.on("validation_needed").stay("run_validation").do(...)
    s.on("validation_passed").to("reporting").when(...)
    s.on("validation_failed").to("implementing").emit(...)
```

Prefer:

- explicit names;
- progressive disclosure: short forms for simple machines, rich forms when
  needed;
- multiline natural-language strings near the state/transition they govern;
- deterministic helpers for crisp logic;
- `nl` helpers only where semantic judgment is needed;
- simple default behavior;
- state-local affordances over global action pools;
- transition actions over hidden entry/exit hooks.

Avoid:

- implicit callbacks;
- magical mutation of context variables;
- YAML behavior that hides its Python binding dependencies;
- unstructured LLM strings where typed records are possible;
- broad catch-and-continue behavior;
- hidden retries outside the underlying ellements clients/tools.

## 32. Deferred features

Explicitly deferred from v1:

- nested/hierarchical states;
- parallel states;
- statecharts/SCXML compatibility;
- visual editor;
- long-running distributed scheduler;
- vector memory integration;
- automatic synthesis of full machines from prose;
- formal verification beyond structural graph validation.

These may be added later if the core remains simple and stable.
