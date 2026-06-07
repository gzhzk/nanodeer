# Evaluation Task Standards

NanoDeer evaluation tasks should make regressions diagnosable, not just visible.
Prefer tasks that encode one clear capability standard and assertions that point
to the failing layer.

## Layered Suites

The evaluation tree is organized into four layers:

```text
contracts     -> system/API/runtime protocols must not break
capabilities  -> individual modules and tools remain usable
behaviors     -> agent policies and strategies follow NanoDeer standards
scenarios     -> realistic high-value user workflows succeed end-to-end
```

## Task Levels

- `contracts`
- `capabilities`
- `behaviors`
- `scenarios`

## Metadata

Use metadata to make reports actionable:

```yaml
capabilities: [file_ops, memory]
behaviors: [evidence_first, tool_recovery]
scenario: ops_log_diagnosis
```

- `capabilities` identify the modules/tools under test.
- `behaviors` identify the agent policy or strategy under test.
- `scenario` identifies a concrete product workflow or business use case.

## Authoring Rules

- State the expected behavior and forbidden behavior in the prompt.
- Prefer deterministic assertions over soft judging.
- Check both the final answer and the trace/tool/file evidence.
- Use structured output files for claims that need exact validation.
- Allow bounded failures only when the task is explicitly testing recovery.
- Add `trace_contract` to every task unless the expected outcome is `wait`; for
  `wait`, set `require_end: false`.

## Useful Assertion Patterns

- Use `tool_sequence` when the agent must gather evidence before writing.
- Use `tool_not_called` for prompt-injection and safety tasks.
- Use `output_not_contains` for poisoned strings.
- Use `file_json_value` for exact structured results.
- Use `event_order` for runtime/API contract checks.
- Use `metric_lte` to set budgets for tool errors, turns, or retries.

## Running Suites

```bash
python -m evaluation.runner
python -m evaluation.runner --suite contracts
python -m evaluation.runner --suite capabilities/file_ops
python -m evaluation.runner --suite behaviors
python -m evaluation.runner --suite scenarios/log_diagnosis
python -m evaluation.runner --suite scenarios --scenario ops_log_diagnosis
python -m evaluation.runner --suite behaviors --behavior tool_recovery
python -m evaluation.runner --suite capabilities --capability memory
```

The JSON report includes grouped summaries by level, suite, category,
capability, behavior, and scenario.
