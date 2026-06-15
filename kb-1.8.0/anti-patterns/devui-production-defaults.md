# Anti-Pattern: Production DevUI With Workshop Defaults

> Status: **Active hazard**
> Affects: `agent-framework-devui` 1.0.0b260528 (and any 1.4+ version)
> Severity: **Critical** — anyone on the network can drive your agent and read its responses

## Symptom

Your DevUI server is hosted on a VM, container, or App Service. It's reachable via a public URL. **Anyone** who finds the URL can:
- Run arbitrary prompts against your agent (cost + data exfil risk)
- See every other user's chat history (no isolation)
- Drive your agent's tools (Bing search, file search, MCP servers) without auth

## Why it's wrong

DevUI is designed for **single-developer local use**. Since 1.4.0 (PR #5740) the defaults are restrictive on purpose:

| Default (1.4+) | Value | Why |
|---------------|-------|-----|
| `host` | `127.0.0.1` | Only loopback — not reachable from other machines |
| `auth_enabled` | `True` | Requires `auth_token` for every request |
| `cors_origins` | `[]` | No cross-origin requests |

To make DevUI usable in a **workshop** (Codespaces port-forward, classroom WiFi, etc.), you must explicitly opt out of all three. The danger: copy-pasting the workshop call into a production deployment.

## Wrong code

```python
# WRONG — production-bound code with workshop defaults
serve(
    entities=[agent],
    host="0.0.0.0",          # public binding
    port=8080,
    auth_enabled=False,      # NO AUTH
    cors_origins=["*"],      # ANY origin
)
```

If this is deployed behind a public LB, your agent is wide open.

## Correct code — Workshop version (with guard)

```python
def _assert_safe_auth(auth_enabled: bool) -> None:
    """Refuse to start with auth_enabled=False unless the user opts in."""
    if not auth_enabled and os.getenv("FOUNDRY_DEVUI_WORKSHOP", "false").lower() != "true":
        raise RuntimeError(
            "DevUI auth is disabled. Set FOUNDRY_DEVUI_WORKSHOP=true to opt in "
            "(workshop / local dev only). NEVER set this in production."
        )

# Workshop deployment:
host = os.getenv("FOUNDRY_DEVUI_HOST", "0.0.0.0")
port = int(os.getenv("FOUNDRY_DEVUI_PORT", "8080"))
auth_enabled = os.getenv("FOUNDRY_DEVUI_AUTH_ENABLED", "false").lower() == "true"

_assert_safe_auth(auth_enabled)

serve(
    entities=[agent],
    host=host,
    port=port,
    auth_enabled=auth_enabled,
    cors_origins=["*"] if not auth_enabled else [],
    auto_open=False,
)
```

## Correct code — Production version

For **production**, don't use DevUI at all. Build a real FastAPI / web app with proper authentication:

```python
# Production: don't use DevUI, build a proper app:
from fastapi import FastAPI, Depends
from fastapi.security import OAuth2AuthorizationCodeBearer

app = FastAPI()
oauth = OAuth2AuthorizationCodeBearer(...)

@app.post("/chat", dependencies=[Depends(oauth)])
async def chat(prompt: str):
    result = await agent.run(prompt)
    return {"text": result.text}
```

If you absolutely must use DevUI in production (e.g., internal-only dashboards):

```python
serve(
    entities=[agent],
    host="127.0.0.1",       # behind an authenticated reverse proxy ONLY
    port=8080,
    auth_enabled=True,
    auth_token=os.environ["DEVUI_AUTH_TOKEN"],   # required strong secret
    cors_origins=[os.environ["DEVUI_ALLOWED_ORIGIN"]],
    auto_open=False,
)
```

## How to detect

```bash
# Scan your code for the dangerous combo:
rg -A3 "serve\(" --type py | rg -B1 "auth_enabled\s*=\s*False"
```

In CI, add a check that production deployments don't set `FOUNDRY_DEVUI_WORKSHOP=true`:

```yaml
- name: Reject workshop flag in production
  run: |
    if [ "$ENVIRONMENT" = "production" ] && [ "$FOUNDRY_DEVUI_WORKSHOP" = "true" ]; then
      echo "FOUNDRY_DEVUI_WORKSHOP must NOT be true in production" >&2
      exit 1
    fi
```

## See also

- [Pattern — `devui-local-development.md`](../patterns/devui-local-development.md)
- [API ref — `devui.md`](../api-reference/1.8.0/devui.md)
