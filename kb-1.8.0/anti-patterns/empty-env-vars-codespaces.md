# Anti-Pattern: Empty-String Env Vars in Codespaces / Dev Containers

> Status: **Active hazard**
> Affects: any Codespaces or VS Code Dev Container setup
> Severity: **Medium** — silent failure, hard to debug, looks like "auth broken"

## Symptom

```python
>>> import os
>>> os.getenv("FOUNDRY_PROJECT_ENDPOINT")
''             # ← empty string, NOT None
>>> len(os.environ["FOUNDRY_PROJECT_ENDPOINT"])
0
```

Then:
```
RuntimeError: project_endpoint cannot be empty
```

…even though you have it set in `.env` and `dotenv.load_dotenv()` runs successfully.

## Why it's wrong

Codespaces / Dev Containers inject **empty-string** placeholders for declared env vars that aren't actually set. Reasons:
- A Codespace defines `FOUNDRY_PROJECT_ENDPOINT` as an "expected variable" but the secret wasn't provisioned.
- A Dev Container `devcontainer.json` has `"containerEnv": { "FOO": "${localEnv:FOO}" }` and `FOO` is unset on the host.

Now: `python-dotenv`'s default `load_dotenv()` **only fills variables that aren't already set**. It does NOT override existing values — including empty strings. So your `.env` content is ignored.

## Wrong code

```python
from dotenv import load_dotenv
import os

load_dotenv()    # No-op for FOUNDRY_PROJECT_ENDPOINT='' (already "set")
endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]    # → ''
```

Or:

```python
from dotenv import load_dotenv
load_dotenv(override=True)     # Works, but stomps on intentional CLI overrides
```

## Correct code — Fill-only loader

```python
import os
from pathlib import Path
from dotenv import dotenv_values

DOTENV = Path(__file__).resolve().parents[1] / ".env"

for k, v in dotenv_values(DOTENV).items():
    if v is None:
        continue
    # Treat empty string the same as unset, but don't stomp on real values.
    if not (os.getenv(k) or "").strip():
        os.environ[k] = v
```

Pair it with a strict require-helper:

```python
def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable is missing or empty: {name}. "
            "Set it via .env / export / Codespaces secrets and try again."
        )
    return value
```

## Why this pattern works

| Behavior | Code path |
|----------|-----------|
| Var is genuinely **unset** (no env var, no `.env`) | Loader skips it (no value in `.env`); `_require_env` raises with actionable message. |
| Var is **set to empty string** (Codespaces placeholder) | Loader treats it as unset and fills from `.env`. |
| Var is **set to a real value** in env (e.g., `FOO=x python ...`) | Loader skips (existing value is non-empty, intentional override preserved). |
| Var is **set in `.env`** with a real value, **unset** in env | Loader fills from `.env`. |

## How to detect

```bash
# Inspect all your env vars and find empty ones:
env | grep -E "^[A-Z]+=$" | sort

# Inside Python:
import os
for k, v in sorted(os.environ.items()):
    if v == "":
        print(f"EMPTY: {k}")
```

## Codespaces / Devcontainer hygiene

- For Codespaces, prefer **secrets** over `containerEnv` for required values. Secrets are not injected when unset; env vars from `containerEnv` are injected as empty strings.
- For Dev Containers, use `"runArgs": ["--env-file=${localWorkspaceFolder}/.env"]` to pass the real `.env` straight to the container instead of relying on `containerEnv` interpolation.

## See also

- [`sync-credential-in-async.md`](sync-credential-in-async.md) — another fail-fast pattern
- [API ref — `clients.md`](../api-reference/1.8.0/clients.md) — `FoundryChatClient` env requirements
