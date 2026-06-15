# Pattern: DevUI Local Development (`serve()`)

> Status: **Stable**
> Pinned: `agent-framework-devui==1.0.0b260528`
> Verified against: parent demo `src/demo6_devui.py`
> See also: [API ref — `devui.md`](../api-reference/1.8.0/devui.md)

## Goal

Launch a **local web UI** to interact with your agents and workflows during development — chat-style turns, tool-call inspection, OTel trace viewer. Ideal for workshops, demos, and rapid iteration.

## When to use

- ✅ You're in a workshop / classroom / local dev session and want to demo agents in a browser.
- ✅ You want to **inspect tool calls** (request body, response, latency) without writing your own UI.
- ❌ Production deployment → use a real web framework + auth. DevUI is dev-only.
- ❌ Headless evaluation pipelines → call `agent.run(...)` directly.

## Code (workshop pattern)

```python
import asyncio
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from agent_framework.devui import serve
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


for k, v in dotenv_values(Path(__file__).resolve().parents[1] / ".env").items():
    if v is not None and not (os.getenv(k) or "").strip():
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


# --- 1. Auth-token guard (workshop-only override) -----------
def _assert_safe_auth(auth_enabled: bool) -> None:
    """
    Catch the most common workshop mistake: AUTH_ENABLED=false + a public host.
    Refuse to start unless the user explicitly opts in with FOUNDRY_DEVUI_WORKSHOP=true.
    """
    if not auth_enabled and os.getenv("FOUNDRY_DEVUI_WORKSHOP", "false").lower() != "true":
        raise RuntimeError(
            "DevUI auth is disabled. This is fine for local workshops, but NOT for "
            "production / shared networks. Set FOUNDRY_DEVUI_WORKSHOP=true to opt in."
        )


# --- 2. Port preflight (give a clearer error than 'address already in use') ---
def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host if host != "0.0.0.0" else "127.0.0.1", port))
            return True
        except OSError:
            return False


async def build_agent():
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")
    cred = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=project_endpoint, model=model, credential=cred
    )
    # NOTE: For DevUI we hand the agent over to serve(); serve() owns its lifetime.
    return await client.as_agent(
        name="assistant",
        instructions="You are a helpful assistant.",
    ).__aenter__()


def main() -> None:
    host = os.getenv("FOUNDRY_DEVUI_HOST", "0.0.0.0")
    port = int(os.getenv("FOUNDRY_DEVUI_PORT", "8080"))
    auth_enabled = os.getenv("FOUNDRY_DEVUI_AUTH_ENABLED", "false").lower() == "true"

    _assert_safe_auth(auth_enabled)

    if _port_in_use(host, port):
        raise RuntimeError(
            f"Port {port} is already bound. Stop the other process or set FOUNDRY_DEVUI_PORT."
        )

    agent = asyncio.run(build_agent())

    serve(
        entities=[agent],
        host=host,
        port=port,
        auto_open=False,
        auth_enabled=auth_enabled,
        cors_origins=["*"],   # workshop-only; tighten for shared deployments
    )


if __name__ == "__main__":
    main()
```

## Why each piece

| Piece | Why |
|-------|-----|
| `_assert_safe_auth(...)` | DevUI tightened defaults in 1.4.0 (`auth_enabled=True`, `host='127.0.0.1'`). Disabling auth on a public host is dangerous, so we **refuse** unless the user opts in explicitly via env var. |
| `_port_in_use(...)` preflight | Without this, the failure mode is a low-level OSError. The preflight gives an actionable message. |
| `host="0.0.0.0"` | Required if you want Codespaces port-forwarding to expose DevUI. **Never** use this in production. |
| `auth_enabled=False` | OK for local workshops only. With `_assert_safe_auth` you can't accidentally ship this. |
| `cors_origins=["*"]` | Lets the browser preview talk to DevUI from arbitrary origins (Codespaces, etc.). Tighten for shared deployments. |
| `auto_open=False` | Don't try to open a browser on the server side (no display in containers). |
| `agent` passed to `serve(entities=[agent])` | DevUI takes an **already-created** agent. It does not own the client/credential — your code does. |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `serve()` with no args in production | 1.4.0+ defaults to `127.0.0.1` + auth enabled, so production-safe by default. Workshop pattern needs explicit `host="0.0.0.0", auth_enabled=False`. |
| `auth_enabled=False` + `host="0.0.0.0"` without the env-guard | Anyone on the network can drive your agent. Always gate via the workshop opt-in. |
| Running DevUI from inside a Codespace and forgetting to forward the port | The browser preview won't load. Forward the port (Codespaces panel → Ports). |
| Creating the agent inside `serve()`'s loop (not before) | Causes "agent already entered" or asyncio loop errors. Build the agent first, then pass it in. |
| Sharing one DevUI across many users without auth | DevUI has zero authorization model. Use auth or isolate per user. |

## Verification

```bash
# 1. Set .env with FOUNDRY_PROJECT_ENDPOINT + FOUNDRY_MODEL + FOUNDRY_DEVUI_WORKSHOP=true.
# 2. Run:
python path/to/this/script.py
# 3. Open http://localhost:8080 (or the forwarded Codespaces URL).
```

Expected: a chat-style UI with your agent registered and clickable.

## See also

- [`devui.md`](../api-reference/1.8.0/devui.md) — full `serve()` reference
- [`../anti-patterns/devui-production-defaults.md`](../anti-patterns/devui-production-defaults.md)
- [`canonical-agent-creation.md`](canonical-agent-creation.md)
