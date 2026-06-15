# Anti-Pattern: Streaming `output` Handler Overwrites Instead of Accumulating

> Status: **Active hazard** (already fixed in this repo's `templates/multi-agent-workflow/` and `examples/arxiv-insights/`)
> Affects: any workflow consuming `event.type == "output"` from `Workflow.run(..., stream=True)`
> Severity: **HIGH** — silent failure; the workflow exits 0 with all `executor_completed` events firing, but the final answer reaches the user empty

## Symptom

`python main.py` finishes successfully (exit 0; researcher / writer / reviewer / finalizer all log `executor_completed`), but the printed final block is empty:

```text
--- FINAL ---


real    0m30.633s
```

Tail of the log also shows the marker `[final output from finalizer]` printed hundreds of times (once per streaming chunk) with **no content between markers**.

This was first observed live during Phase 5a Live Test S2.1 on 2026-05-30 against `agent-framework-foundry==1.8.0` with deployment `gpt-5-4`.

## Why it's wrong

In Agent Framework 1.8.0, when a final-output executor (anything listed in `WorkflowBuilder(..., output_from=[...])`) streams its response, the workflow emits a **`WorkflowEvent(type="output")` per streaming chunk** — not once per executor. The full event-type table is in [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md#workflowevent--the-18-event-types).

Naive handlers that **assign** instead of append fall into three compounded traps on the same branch:

1. **Overwrite, not accumulate** — `final_output = _format_payload(event.data)` on every chunk → after the loop, `final_output` holds whichever chunk arrived last, typically an empty completion sentinel.
2. **Marker printed per chunk** — `print(f"[final output from {event.executor_id}]")` runs for every chunk, producing a wall of repeated headers.
3. **Chunk content never printed inline** — the chunk is captured in a local variable but no `print(chunk, ...)` is emitted as it arrives. The user sees no streaming progress, then nothing at the end.

The same workflow's `intermediate` branch usually does the right thing (it prints `event.data` directly as each chunk arrives), so researcher / writer / reviewer outputs ARE visible — masking how badly the `output` branch is broken.

## Wrong code

```python
final_output = ""
async for event in wf.run(question, stream=True):
    if event.type == "intermediate":
        chunk = _format_payload(event.data)
        print(chunk, end="", flush=True)
    elif event.type == "output":
        final_output = _format_payload(event.data)            # ❌ overwrite
        print(f"\n[final output from {event.executor_id}]\n") # ❌ prints per chunk
        # ❌ chunk content never printed inline

print("\n--- FINAL ---")
print(final_output)   # → empty string
```

## Correct code

```python
final_output = ""
final_marker_printed = False

async for event in wf.run(question, stream=True):
    if event.type == "intermediate":
        chunk = _format_payload(event.data)
        print(chunk, end="", flush=True)
    elif event.type == "output":
        chunk = _format_payload(event.data)
        if chunk:
            if not final_marker_printed:
                print(f"\n[final output from {event.executor_id}]\n", flush=True)
                final_marker_printed = True
            final_output += chunk              # ✅ accumulate
            print(chunk, end="", flush=True)   # ✅ stream inline

print("\n--- FINAL ---")
print(final_output)
```

Three changes pin the fix in place:

| Change | Why |
|---|---|
| `final_output += chunk` | Preserves every streamed chunk; the loop assembles the complete final answer. |
| `final_marker_printed` flag, gated on the first **non-empty** chunk | Header prints exactly once, only when there's real content to follow. Empty leading chunks no longer trigger a phantom header. |
| `print(chunk, end="", flush=True)` inside the `output` branch | Restores streaming UX — the user sees the final answer appearing token by token, the same way `intermediate` chunks do. |

The shipped canonical implementations are at:

- [`templates/multi-agent-workflow/main.py`](../../templates/multi-agent-workflow/main.py) (L154-L164)
- [`examples/arxiv-insights/main.py`](../../examples/arxiv-insights/main.py) (`output` branch in the streaming event loop)

## Why this pattern works

| Scenario | Behavior with the correct handler |
|---|---|
| Final executor streams 200 chunks | Marker prints once on the first non-empty chunk; chunks stream inline; `final_output` ends up with the full concatenation. |
| Final executor emits a single non-streamed event | Marker prints once; chunk prints once; `final_output` equals that chunk. |
| First chunk is empty (warm-up / completion sentinel) | Marker is **not** printed yet; `final_output` stays `""`; the loop waits for real content. |
| Workflow has multiple `output_from=[...]` executors | Each non-empty chunk for each executor is accumulated. (If you need to separate them, gate `final_marker_printed` on `event.executor_id` instead of a single bool.) |
| `event.type == "data"` (deprecated alias for `"intermediate"`) | Belongs to the intermediate branch, not the output branch — handle alongside `"intermediate"`. |

## How to detect

Source-code grep for any `output` handler that assigns rather than appends:

```bash
# Inside the file under review
grep -nE 'event\.type\s*==\s*"output"' main.py | head
# Then visually scan the next ~10 lines for `final_output = ` (assign) vs `final_output += ` (accumulate)
```

Programmatic (AST-level) detection of both bugs lives in [`tests/test_template_multi_agent_workflow_f2.py`](../../tests/test_template_multi_agent_workflow_f2.py):

- `test_output_event_branch_accumulates_final_output` — asserts an `ast.AugAssign(op=Add, target=Name('final_output'))` exists inside the `output` branch AND no plain `ast.Assign` to `final_output` exists in that branch.
- `test_output_marker_is_printed_only_once` — asserts a `final_marker_printed = False` initialization exists before the event loop AND the marker print is guarded by `if not final_marker_printed:`.

Mirror these two asserts in any new workflow template's own AST test.

## See also

- [`../patterns/multi-agent-workflow.md`](../patterns/multi-agent-workflow.md) — full canonical workflow with the corrected handler in context.
- [`../api-reference/1.8.0/workflows.md`](../api-reference/1.8.0/workflows.md#workflowevent--the-18-event-types) — `WorkflowEvent.type` reference, including the `"intermediate"` / `"data"` alias and the `"output"` semantics for `output_from=[...]` executors.
- [`workflow-event-isinstance.md`](workflow-event-isinstance.md) — the related anti-pattern of using `isinstance(event, …)` instead of `event.type ==`.
- [`removed-apis-since-1.0.md`](removed-apis-since-1.0.md) — `Workflow.run_stream` was removed in 1.5.0; the canonical streaming entry point is `Workflow.run(..., stream=True)`.
