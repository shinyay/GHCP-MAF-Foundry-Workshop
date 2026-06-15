# DevUI (`agent_framework.devui.serve`)

> Status: **Stable** for the API surface, but on a **date-based beta track** (`agent-framework-devui==1.0.0b260528`), NOT a 1.x pinned release.
> Pinned in this template: `agent-framework-devui==1.0.0b260528`
> Verified against: introspection of `serve()` signature + parent demo `src/demo6_devui.py`

DevUI is a local web UI for exploring an agent or workflow during development. It exposes:

- A chat panel to talk to the agent / drive the workflow
- A tracing panel showing tool calls and intermediate events
- A debug panel for inspecting requests / responses

Use it during **development only** — never expose `serve()` to the public Internet.

---

## Install

```bash
pip install "agent-framework-devui==1.0.0b260528"
```

> [!IMPORTANT]
> The `agent-framework-devui` package is on a **date-coded beta**, not 1.x. Pin the exact build you tested against — newer betas may change the `serve()` signature without bumping a major version.

---

## `serve(...)` signature (1.0.0b260528)

```python
def serve(
    *,
    entities: list[Agent | Workflow],
    entities_dir: str | os.PathLike | None = None,
    port: int = 8080,
    host: str = "127.0.0.1",
    auto_open: bool = False,
    cors_origins: list[str] | None = None,
    ui_enabled: bool = True,
    instrumentation_enabled: bool = False,
    mode: Literal["developer", "user"] = "developer",
    auth_enabled: bool = True,
    auth_token: str | None = None,
) -> None
```

| Param | Default | Notes |
|-------|---------|-------|
| `entities` | required | List of agents / workflows to expose. Each becomes a tab in the UI. |
| `entities_dir` | None | If set, DevUI auto-discovers agents from this directory. |
| `port` | `8080` | TCP port. |
| `host` | `"127.0.0.1"` | **Tightened in 1.4.0** (PR #5740). Use `"0.0.0.0"` for Codespaces / remote browser. |
| `auto_open` | `False` | If True, opens the default browser to the URL on start. |
| `cors_origins` | `None` | List of allowed origins. Use `["*"]` for workshop / local-only. |
| `ui_enabled` | `True` | Set False to expose only the JSON API (e.g. for headless integration tests). |
| `instrumentation_enabled` | `False` | Whether DevUI itself emits OTel spans. |
| `mode` | `"developer"` | `"developer"` shows debug panels; `"user"` hides them. |
| `auth_enabled` | `True` | **Tightened in 1.4.0** (PR #5740). True means an auth token is required. |
| `auth_token` | `None` | Required token when `auth_enabled=True`. If `auth_enabled=True` and `auth_token` is empty, all requests get 401 with no useful error. **Guard against this**. |

---

## Workshop / local-dev pattern (canonical)

From parent demo `src/demo6_devui.py`:

```python
from agent_framework.devui import serve

# Allow VS Code port-forwarded URL from Codespaces to reach the UI
serve(
    entities=[workflow],
    host="0.0.0.0",                  # NOT the default 127.0.0.1
    port=8080,
    auto_open=True,
    auth_enabled=False,              # NOT the default True
    cors_origins=["*"],
)
```

> [!IMPORTANT]
> **Never use these defaults in production.** `host="0.0.0.0"` + `auth_enabled=False` + `cors_origins=["*"]` is appropriate for an isolated dev container only. For shared environments, use the production pattern below.

### Guard against the auth-token misconfig

If `auth_enabled=True` but `auth_token` is empty, DevUI accepts both kwargs and silently returns 401 for every API call — the UI looks "broken" with no actionable error. Add a precheck:

```python
if auth_enabled and not auth_token:
    raise RuntimeError(
        "auth_enabled=True requires a non-empty auth_token. "
        "Either set auth_token, or set auth_enabled=False for local-only use."
    )
```

The parent demo does this at lines 42-50.

---

## Production-ish pattern

```python
import os
import secrets

serve(
    entities=[my_agent],
    host="127.0.0.1",                          # localhost only
    port=int(os.getenv("DEVUI_PORT", "8080")),
    auth_enabled=True,
    auth_token=os.environ["DEVUI_AUTH_TOKEN"], # required, validated
    cors_origins=["https://internal-dashboard.corp.example.com"],
    mode="user",                               # hide developer panels
    instrumentation_enabled=True,              # send traces to your APM
)
```

For real production, put DevUI behind a reverse proxy (nginx / Application Gateway) that handles TLS termination and auth — DevUI's auth is meant as a development guardrail, not a hardened auth system.

---

## Port preflight (avoid Errno 98)

If the port is already bound, uvicorn raises `OSError: [Errno 98] Address already in use` — friendly only if you check first:

```python
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
except OSError as ex:
    if getattr(ex, "errno", None) == 98:
        raise RuntimeError(
            f"DevUI cannot start: {host}:{port} is already in use. "
            f"Set DEVUI_PORT=<other-port> and retry."
        ) from ex
    raise
finally:
    sock.close()

serve(entities=[...], host=host, port=port, ...)
```

This is the parent demo pattern (`src/demo6_devui.py` lines 54-68).

---

## Entities = agents OR workflows

DevUI accepts both, mixed:

```python
serve(entities=[my_agent, my_workflow])
```

Each appears as a separate tab. Workflows show the executor DAG visually.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Using default `host='127.0.0.1'` from Codespaces | Set `host='0.0.0.0'` so VS Code's port-forward URL can reach it. |
| Leaving `auth_enabled=True` with no `auth_token` | All requests 401. Either set token or `auth_enabled=False`. |
| Default `cors_origins=None` while serving from a different origin | Set `cors_origins=["*"]` locally or list the exact origin in production. |
| `host="0.0.0.0", auth_enabled=False` in production | **Public unauthenticated access.** Lock down before deploying. |
| Pinning to `agent-framework-devui` without version | Beta surface — pin to the exact `1.0.0b<date>` you tested against. |

---

## See also

- [`packages.md`](packages.md) — beta pinning rationale
- [`observability.md`](observability.md) — `instrumentation_enabled` interaction
- [`../../patterns/devui-local-development.md`](../../patterns/devui-local-development.md) — full workshop recipe
- [`../../anti-patterns/devui-production-defaults.md`](../../anti-patterns/devui-production-defaults.md)
- Upstream PR (1.4 defaults tightening): [microsoft/agent-framework#5740](https://github.com/microsoft/agent-framework/pull/5740)
