# ellements-cli

`ellements-cli` contributes `ellements.cli`: reusable terminal presentation
pieces for command-line apps and small agent TUIs. It is not a product shell by
itself. It is the place where terminal chrome, stdout/stderr discipline, slash
commands, and Textual wiring live so other apps do not reimplement them.

## Principles

- **Pipelines stay clean.** `CliPrinter` sends status, headers, panels, and
  progress to stderr; primary data goes to stdout.
- **Presentation is pluggable.** `EventRenderer`, `AgentRunner`, `SaveHandler`,
  `PersonaProvider`, and `GuidelineProvider` are protocols.
- **The TUI is application-agnostic.** `AgentTUI` knows how to run a query,
  show progress, save output, and switch modes; it does not know what the agent
  means.
- **State is explicit.** TUI modal state is one `Mode` enum, not scattered
  booleans.
- **Small components first.** Rich renderers in `components.py` remain usable
  without the higher-level `CliPrinter` or Textual app.

## Structure

| Module | Role |
| --- | --- |
| `components.py` | Stateless Rich renderers for panels, messages, issues, stats, and results |
| `printer.py` | `CliPrinter` and `EventRenderer` for branded CLI workflows |
| `agent_tui.py` | `AgentTUI`, `TuiConfig`, slash commands, runner/save/provider protocols |
| `adapters.py` | Bridges core persona/guideline libraries and controllers into TUI providers |

## Examples

```python
from ellements.cli import CliPrinter

printer = CliPrinter("Prompt Composer", icon="*")
printer.header({"Model": "openai/gpt-4.1"})
printer.status("Composing prompt")

result = await compose_prompt()
printer.result_markdown(result)
printer.done()
```

```python
from ellements.cli import AgentRunner, AgentTUI, RunResult, TuiConfig


class Runner:
    async def run(self, query: str, controls) -> RunResult:
        controls.progress("Working...")
        answer = await answer_query(query)
        return RunResult(text=answer, stats={"queries": 1})


app = AgentTUI(
    TuiConfig(
        agent_name="Researcher",
        agent_description="Small research helper",
        runner=Runner(),
    )
)
app.run()
```

## Extending

Add low-level rendering to `components.py`; add workflow-level terminal behavior
to `CliPrinter`; add interactive state to `AgentTUI` only when it applies across
apps. Keep stdout reserved for machine-consumable output. If a UI needs
domain-specific panels, provide a custom widget rather than baking that domain
into the generic TUI.
