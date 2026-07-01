# Current State

## Current Prompt Specification

The prompt specification below might be either from the first turn or subsequent turns, depending on the conversation history. The first turn contains the initial prompt specification, while subsequent turns may contain additional elements indicated by XML-like tags, as explained before.

```
{{prompt_spec}}
```

## Current Variables

{{#variables}}
- `{{key}}`: {{value}}
{{/variables}}
{{^variables}}
No variables provided.
{{/variables}}

Process the prompt specification above using the directives and variable values provided. Produce the final composed prompt.

Your response MUST use the required `<output>...</output>` XML format, including the `<analysis>` tag (high-level rationale only; may be empty).

During processing, for each iteration pass (variable substitution + directive execution), you MUST call `log_transition(text)` exactly once. The `text` must include both what changed and why; if nothing changed, `no change` is valid (still include a brief reason).