# Anti-Pattern: Using Sync `AzureCliCredential` in an Async Agent

> Status: **Active hazard**
> Affects: 1.0.0 → 1.8.0 (all versions — Python async-await fundamental)
> Severity: **Medium** — blocks the event loop, hard-to-diagnose latency, may leak HTTP sessions

## Symptom

- The first agent call takes **2-10 seconds longer** than expected.
- Concurrent calls run **sequentially** instead of in parallel.
- Shutdown warnings:
  ```
  Unclosed client session
  Unclosed connector
  ```
- Tests using `pytest-asyncio` hang or time out intermittently.

## Why it's wrong

`azure.identity.AzureCliCredential` is a **synchronous** client. When you `await` something that internally uses it (like `FoundryChatClient.get_chat_completion(...)`), the credential's HTTP call blocks the event loop the entire time it's running — typically the 2-5 second `az` token fetch.

This:
1. **Defeats async** — other coroutines can't run while the credential blocks.
2. **Leaks connections** — the sync credential's `requests`-based HTTP pool isn't a Python context manager that integrates with `async with`, so connections aren't released cleanly at shutdown.
3. **Hides errors** — token-fetch errors fire at the wrong layer of the stack and produce confusing tracebacks.

The fix is mechanical: use `azure.identity.aio.AzureCliCredential` instead.

## Wrong code

```python
from azure.identity import AzureCliCredential   # ← SYNC version

async def main():
    cred = AzureCliCredential()                  # ← no async lifecycle
    client = FoundryChatClient(
        project_endpoint=...,
        model=...,
        credential=cred,
    )
    async with client.as_agent(...) as agent:
        result = await agent.run("hi")
    # cred is never explicitly closed.
```

## Correct code

```python
from azure.identity.aio import AzureCliCredential   # ← ASYNC version

async def main():
    async with AzureCliCredential() as cred:        # ← async context manager
        client = FoundryChatClient(
            project_endpoint=...,
            model=...,
            credential=cred,
        )
        async with client.as_agent(...) as agent:
            result = await agent.run("hi")
        # cred closed automatically on exit.
```

The pattern: **every credential type in `azure.identity` has a mirror in `azure.identity.aio`** with the same constructor signature. Always use the `.aio` version inside `async def`.

## How to detect

```bash
# Find the wrong imports:
rg "from azure\.identity import" --type py

# Anything that imports from azure.identity (without .aio) inside an async function is suspect.
```

A targeted check:

```bash
rg -l "async def" --type py | xargs rg -l "from azure\.identity import" | xargs -I{} echo "Suspect file: {}"
```

A linter rule (custom):

```python
# scripts/lint_async_credential.py
import ast
import sys
from pathlib import Path

class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.has_async_def = False
        self.uses_sync_credential = False
    def visit_AsyncFunctionDef(self, node):
        self.has_async_def = True
        self.generic_visit(node)
    def visit_ImportFrom(self, node):
        if node.module == "azure.identity":
            self.uses_sync_credential = True

for p in Path("src").rglob("*.py"):
    tree = ast.parse(p.read_text())
    v = Visitor()
    v.visit(tree)
    if v.has_async_def and v.uses_sync_credential:
        print(f"[lint] {p}: sync credential in async file", file=sys.stderr)
        sys.exit(1)
```

## Exception: `DefaultAzureCredential`

The same rule applies: use `azure.identity.aio.DefaultAzureCredential`, not `azure.identity.DefaultAzureCredential`, inside async code.

## See also

- [`missing-async-with-cleanup.md`](missing-async-with-cleanup.md)
- [`empty-env-vars-codespaces.md`](empty-env-vars-codespaces.md)
- [API ref — `clients.md`](../api-reference/1.8.0/clients.md)
