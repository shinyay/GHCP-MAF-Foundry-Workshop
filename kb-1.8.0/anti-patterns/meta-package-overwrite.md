# Anti-Pattern: Installing the `agent-framework` Meta Package

> Status: **Active hazard**
> Affects: 1.0.0 → 1.8.0
> Severity: **High** — silently overwrites your namespace and breaks imports

## Symptom

```
ModuleNotFoundError: No module named 'agent_framework.foundry'
```

or

```
AttributeError: module 'agent_framework' has no attribute 'WorkflowBuilder'
```

…after you ran what looked like the right command:

```bash
pip install agent-framework
```

## Why it's wrong

The `agent-framework` package on PyPI is a **meta-package** that depends on **multiple** runtime packages (`agent-framework-core`, `agent-framework-foundry`, `agent-framework-azureopenai`, etc.).

The issue: those subpackages each contain their own `agent_framework/__init__.py`. When pip installs them in sequence, the **last one wins**, overwriting the namespace from the previous installs. The exact failure depends on install order — often you end up with `agent_framework/__init__.py` from `agent-framework-core` and `agent_framework.foundry` is missing or stale.

The result: imports that worked on your colleague's machine fail mysteriously on yours.

## Wrong code

`requirements.txt`:
```
agent-framework==1.8.0   # ← DON'T
```

or:
```bash
pip install agent-framework
```

## Correct code

Pick **exactly one** runtime package based on what you need:

`requirements.txt`:
```
agent-framework-foundry==1.8.0   # Foundry users (most common)
# OR
agent-framework-azureopenai==1.8.0   # Azure OpenAI direct
# OR
agent-framework-openai==1.8.0   # OpenAI public API
```

Then add optional add-ons individually if needed (these are safe to mix because they put themselves under `agent_framework.<subname>`):

```
agent-framework-devui==1.0.0b260528   # DevUI (beta track)
agent-framework-azurefunctions==1.8.0   # Azure Functions integration
agent-framework-orchestrations==1.8.0   # Orchestration helpers
agent-framework-a2a==1.8.0   # Agent-to-Agent protocol
```

## How to detect

```bash
# Inspect what your environment actually has:
pip list | grep agent-framework
```

If you see `agent-framework` (no suffix) in the list, **uninstall it**:

```bash
pip uninstall -y agent-framework
pip install --force-reinstall agent-framework-foundry==1.8.0
```

For new repos, add a CI check:

```bash
# In CI:
if pip show agent-framework > /dev/null 2>&1; then
  echo "ERROR: meta package 'agent-framework' is installed — replace with agent-framework-foundry" >&2
  exit 1
fi
```

## See also

- [API ref — `packages.md`](../api-reference/1.8.0/packages.md)
- [`removed-apis-since-1.0.md`](removed-apis-since-1.0.md)
