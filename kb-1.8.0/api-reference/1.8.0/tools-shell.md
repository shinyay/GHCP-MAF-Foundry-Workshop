# Tools: Shell — hosted container, OpenAI local, and `agent-framework-tools`

> Status: see per-section tags below — the **factory** (`client.get_shell_tool(...)`) is **Stable**; the cross-platform local executor (`LocalShellTool`) ships in a **separate alpha-versioned package** (`agent-framework-tools 1.0.0a*`).
> Pinned: `agent-framework-foundry==1.8.0`, `agent-framework-tools==1.0.0a260424` (alpha; pin to exact version)
> Verified against: upstream samples [`local_shell_with_allowlist.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/local_shell_with_allowlist.py), [`local_shell_with_environment_provider.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/local_shell_with_environment_provider.py), [`client_with_local_shell.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/providers/openai/client_with_local_shell.py), [`client_with_shell.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/providers/openai/client_with_shell.py); source [`agent_framework_tools/shell/_tool.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_tool.py), [`_docker.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_docker.py), [`_policy.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_policy.py)

There are **three distinct shell options** in the 1.8.0 ecosystem. They are easy to confuse because all three reach a shell, but they have very different security profiles and run in very different places.

| Option | Where commands run | Package | Stability | When to use |
|---|---|---|---|---|
| **Hosted shell** | OpenAI-managed container | `agent-framework` (Foundry/OpenAI client) | Stable | OpenAI Responses API; you want zero local execution and don't need filesystem access |
| **Local function-backed shell** (`LocalShellTool`) | Your Python process's user | `agent-framework-tools` (alpha) | Alpha (separate wheel) | Trusted dev workflows; CLI assistants; coding agents |
| **Docker-isolated shell** (`DockerShellTool`) | Short-lived container on your host | `agent-framework-tools` (alpha) | Alpha (separate wheel) | Untrusted input; production with isolation requirements |

Cited: `get_shell_tool(func=None)` returns a hosted declaration; `get_shell_tool(func=<callable>)` returns a local `FunctionTool`. See [`openai/agent_framework_openai/_chat_client.py:L1083-L1170`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/openai/agent_framework_openai/_chat_client.py#L1083) (the `get_shell_tool` factory; inherited by `FoundryChatClient`).

> [!IMPORTANT]
> The `agent-framework-tools` package is currently at version `1.0.0a260424` and is classified as **Development Status :: 3 - Alpha** in its [`pyproject.toml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/pyproject.toml). Pin the **exact** version in `requirements.txt`; the API may change between alphas. The `LocalShellTool` class itself is **not** wrapped in `@experimental(...)` — the warning model in [`feature-stages.md`](feature-stages.md) does not apply here; the entire package is staged via its alpha version number.

---

## 1. Hosted shell (OpenAI container)

> Status: **Stable** (factory)
> Where it runs: OpenAI-managed sandboxed container
> Verified against: [`client_with_shell.py:L25-L60`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/providers/openai/client_with_shell.py#L25-L60)

When `func` is **not** passed, `get_shell_tool(...)` returns a hosted shell declaration. The model's shell calls execute inside an OpenAI-managed container — your process never sees the commands.

```python
import asyncio
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient


async def main() -> None:
    client = OpenAIChatClient(model="gpt-5.4-nano")
    # Hosted (no func) — runs inside OpenAI's container
    shell_tool = client.get_shell_tool()

    agent = Agent(
        client=client,
        instructions="You can run shell commands in a sandboxed container.",
        tools=shell_tool,
    )

    result = await agent.run("Use a shell command to show the current date and time.")
    print(result.text)


asyncio.run(main())
```

**Signature** ([`_chat_client.py:L1083-L1170`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/openai/agent_framework_openai/_chat_client.py#L1083)):

```python
def get_shell_tool(
    *,
    func: Callable[..., Any] | FunctionTool | None = None,
    environment: Literal["auto"] | dict[str, Any] | None = "auto",
    name: str | None = None,
    description: str | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
) -> Any: ...
```

* `environment="auto"` (default) → `{"type": "container_auto"}` (OpenAI picks the container).
* `environment={"type": "container_auto", "file_ids": ["file-abc"]}` → seed the container with previously-uploaded files.
* `environment={"type": "local"}` with **`func=None`** raises `ValueError("Local shell requires func. Provide func for local execution.")` — local execution requires a callable.

**Model support**: not all OpenAI models accept the shell tool. Check the [OpenAI model docs](https://developers.openai.com/api/docs/models/) before deploying.

**Reading hosted shell output** ([`client_with_shell.py:L55-L65`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/providers/openai/client_with_shell.py#L55-L65)):

```python
for message in result.messages:
    shell_calls = [c for c in message.contents if c.type == "shell_tool_call"]
    shell_results = [c for c in message.contents if c.type == "shell_tool_result"]
    if shell_calls:
        print(f"Shell commands: {shell_calls[0].commands}")
    if shell_results and shell_results[0].outputs:
        for output in shell_results[0].outputs:
            if output.stdout:
                print(f"Stdout: {output.stdout}")
```

> [!NOTE]
> The hosted-shell factory is **inherited** by `FoundryChatClient` from `OpenAIChatClient`. Whether the hosted container path is actually wired through to Foundry's backend (vs being an OpenAI-Responses-only feature exposed by inheritance) is **not** validated in this template. If you need a hosted shell on Foundry, prefer either the **OpenAI Responses path** above (where the sample exists) or the **local function-backed path** (Section 2). For Foundry, the **Code Interpreter** factory ([`tools-hosted.md`](tools-hosted.md#code-interpreter)) is the safer choice when "sandboxed code execution" is what you want.

---

## 2. Local function-backed shell (`LocalShellTool`)

> Status: **Alpha** — entire `agent-framework-tools` package; pin exact version
> Where it runs: your Python process's user, on your host
> Package: `agent-framework-tools==1.0.0a260424` (PyPI: [`agent-framework-tools`](https://pypi.org/project/agent-framework-tools/))
> Verified against: [`local_shell_with_allowlist.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/local_shell_with_allowlist.py), [`client_with_local_shell.py`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/providers/openai/client_with_local_shell.py); source [`_tool.py:L63-L170`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_tool.py#L63-L170)

This is the **cross-platform local executor** that ships in the separate `agent-framework-tools` wheel. You construct a `LocalShellTool`, wrap it with `client.get_shell_tool(func=shell.as_function())`, and pass it to the agent.

### Install

```bash
pip install "agent-framework-tools==1.0.0a260424"
```

Hard transitive deps (per [`pyproject.toml`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/pyproject.toml)):

* `agent-framework-core>=1.2.2,<2`
* `psutil>=5.9` — required, not optional. Powers cross-OS process-tree termination on timeout. On Windows in particular, without `psutil` child processes can survive timeout. The package treats this as security-relevant.

### Default-safe usage (approval required)

```python
import asyncio
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_tools.shell import LocalShellTool


async def main() -> None:
    client = OpenAIChatClient(model="gpt-5.4-nano")

    async with LocalShellTool() as shell:  # defaults: mode="persistent", approval_mode="always_require"
        agent = Agent(
            client=client,
            instructions="You can run shell commands to help the user.",
            tools=[client.get_shell_tool(func=shell.as_function())],
        )
        # First run will surface user_input_requests — see the approval loop below.
        result = await agent.run("Run `python --version` and show only the output.")
        print(result.text)


asyncio.run(main())
```

By default, **every command** the model emits goes through approval and is surfaced as a `user_input_request` on the `AgentResponse`. The host application decides whether to approve.

### `LocalShellTool` parameters (source-verified)

Source: [`_tool.py:L154-L170`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_tool.py#L154-L170)

| Parameter | Default | Effect |
|---|---|---|
| `mode` | `"persistent"` | `"persistent"` keeps one long-lived shell subprocess so `cd` / `export` carry across calls. `"stateless"` spawns a fresh subprocess per call. |
| `shell` | platform default | Optional shell argv override. Defaults to `pwsh`/`powershell` on Windows, `bash`/`sh` on Unix. Also overridable via `AGENT_FRAMEWORK_SHELL` env var. |
| `workdir` | cwd | Working directory for commands. |
| `confine_workdir` | `True` | In persistent mode, prefixes each command with `cd <workdir>`. **This is a re-anchor, not hard confinement** — `cd /tmp && rm -rf .` still reaches `/tmp` once. Only `DockerShellTool` or OS-level sandboxing (containers, microVMs, jails) provides hard process/filesystem confinement; `ShellPolicy` is a regex-based UX pre-filter, not a security boundary. |
| `env` | inherit | Seed environment. In `"stateless"` mode replaces child env unless `clean_env=False`. |
| `clean_env` | `False` | If `True`, do **not** inherit `os.environ`; only `env=` is visible. |
| `policy` | `ShellPolicy()` (empty — allows everything) | `ShellPolicy` with `denylist` / `allowlist` regex patterns. **UX pre-filter, not a security boundary.** |
| `timeout` | `30.0` seconds | Per-command timeout. `None` disables. |
| `max_output_bytes` | `65536` (64 KiB) | Combined stdout/stderr cap before truncation. |
| `approval_mode` | `"always_require"` | Sets `FunctionTool.approval_mode` on the returned tool. **The actual security boundary** — and even then only when the host application enforces approval. |
| `acknowledge_unsafe` | `False` | Required to be `True` if you set `approval_mode="never_require"`. Without it, `__init__` raises `ValueError` with explicit hazard text. |
| `on_command` | `None` | Optional audit callback `Callable[[str], None]` fired for every command that passes policy. |

**Persistent mode is single-session.** From the upstream docstring ([`_tool.py:L80-L101`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_tool.py#L80)):

> A persistent-mode `LocalShellTool` is owned by a single conversation / agent session — i.e. one user. The backing shell process carries mutable state (cwd, exported variables, shell history, background jobs) that every subsequent command can observe, and a single stdin/stdout pipe serializes every call. Do not share one instance across users, tenants, or concurrent conversations: state leaks between them and commands queue behind each other. Create one tool per session, close it (or use `async with`) when the session ends. If a shared instance is genuinely required, construct with `mode="stateless"` so each call spawns a fresh subprocess.

### Approval loop (host application)

Verified pattern from [`client_with_local_shell.py:L72-L107`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/providers/openai/client_with_local_shell.py#L72):

```python
async def run_with_approvals(query: str, agent: Agent) -> Any:
    current_input: str | list[Any] = query
    while True:
        result = await agent.run(current_input)
        if not result.user_input_requests:
            return result

        next_input: list[Any] = [query]
        for user_input_needed in result.user_input_requests:
            print(
                f"\nShell request: {user_input_needed.function_call.name}"
                f"\nArguments: {user_input_needed.function_call.arguments}"
            )
            # Ask the operator
            decision = input("Approve? [y/N] ").strip().lower()
            approved = decision == "y"
            next_input.append(user_input_needed.create_response(approved))

        current_input = next_input
```

The agent loops until no `user_input_requests` remain. The host application's decision logic is where the **real security boundary** lives — not in `ShellPolicy`, not in `approval_mode`, but in *how the host responds to the approval prompt*.

### Auto-approve with a strict allow-list

Verified against [`local_shell_with_allowlist.py:L24-L48`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/local_shell_with_allowlist.py#L24):

```python
from agent_framework_tools.shell import LocalShellTool, ShellPolicy

shell = LocalShellTool(
    mode="stateless",
    approval_mode="never_require",
    acknowledge_unsafe=True,  # required when approval is off
    policy=ShellPolicy(
        allowlist=[
            r"^ls(\s|$)",
            r"^pwd$",
            r"^cat\s[^|;&]+$",          # no shell metacharacters in args
            r"^git\s+(status|log|diff)(\s|$)",
            r"^python\s+--version$",
        ],
    ),
    timeout=10,
)
```

This is the **safest fully-automatic configuration**. Every command must match an allow-list regex; the deny-list (empty here) would still win if set. Approval is off because the allow-list is doing the gating.

> [!IMPORTANT]
> `ShellPolicy` patterns are matched against the raw command string with `re.search` (case-insensitive). They are **not** a shell parser. `cat foo.txt; rm -rf /` matches `^cat\s[^|;&]+$` only because the `;` is in the deny set — design your regexes to reject shell metacharacters explicitly, or use `mode="stateless"` + `DockerShellTool` for untrusted input.

### `ShellPolicy` evaluation order

Source: [`_policy.py:L70-L120`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_policy.py#L70-L120)

```python
@dataclass
class ShellPolicy:
    denylist: Sequence[PatternLike] = field(default_factory=tuple)
    allowlist: Sequence[PatternLike] | None = None
    custom: Callable[[ShellRequest], ShellDecision | None] | None = None
```

Evaluation order (first hit wins):

1. **Empty / whitespace-only command** → deny.
2. **`denylist` match** → deny (regardless of allowlist).
3. **`allowlist` is set AND no pattern matches** → deny.
4. **`custom` returns a non-`None` `ShellDecision`** → that decision.
5. **Otherwise** → allow.

Defaults are **empty**: bare `ShellPolicy()` allows every non-empty command. The package intentionally does not ship default deny patterns; the upstream design treats policy as a UX pre-filter and pushes the real boundary to either `approval_mode="always_require"` or `DockerShellTool`.

### Context provider: tell the model what shell it's on

`ShellEnvironmentProvider` probes the underlying shell once and injects a context block describing shell family, OS, working directory, and a configurable list of CLI tool versions. This helps the model emit commands in the right idiom (e.g. PowerShell vs bash). Verified against [`local_shell_with_environment_provider.py:L60-L75`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/samples/02-agents/tools/local_shell_with_environment_provider.py#L60).

```python
from agent_framework_tools.shell import (
    LocalShellTool,
    ShellEnvironmentProvider,
    ShellEnvironmentProviderOptions,
)

options = ShellEnvironmentProviderOptions(
    probe_tools=("git", "python", "uv", "node"),
)

async with LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True) as shell:
    provider = ShellEnvironmentProvider(shell, options)
    agent = Agent(
        client=client,
        instructions="Use the shell tool to answer the user's question.",
        tools=[client.get_shell_tool(func=shell.as_function())],
        context_providers=[provider],
    )
```

The snapshot is captured on first use of the provider and is accessible via `provider.current_snapshot` for logging.

---

## 3. Docker-isolated shell (`DockerShellTool`)

> Status: **Alpha** (same `agent-framework-tools` package)
> Where it runs: a short-lived Docker / Podman container on your host
> Verified against: source [`_docker.py:L258-L450`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_docker.py#L258)

When the model's input is **untrusted** (it comes from end users, the web, a queue) and you need **filesystem isolation**, use `DockerShellTool`. The container is the intended boundary — unlike `LocalShellTool`, approval is not the only line of defense.

```python
from agent_framework_tools.shell import DockerShellTool

async with DockerShellTool(
    # image=...  # omit to use the upstream default (a small MS-maintained base with bash + sleep);
                 # supply your own with `image="mcr.microsoft.com/azurelinux/base/core:3.0"` or similar.
    network="none",                # default — no network egress
    user="65534:65534",            # default — non-root (nobody)
    read_only_root=True,           # default — rootfs is read-only
    mount_readonly=True,           # default — host_workdir mounted ro
    memory="512m",
    pids_limit=64,
    timeout=60,
) as shell:
    agent = Agent(
        client=client,
        instructions="You can run shell commands in an isolated container.",
        tools=[client.get_shell_tool(func=shell.as_function())],
    )
```

> [!IMPORTANT]
> If you override `image=`, the image must contain `bash` (or whatever you set `shell` to) **and** `sleep` (for `mode="persistent"`, the tool keeps the container alive by `sleep`-ing). Pure-distroless images without a shell will fail at first command. Test new images first with `mode="stateless"`.

### `DockerShellTool` defaults that matter

| Parameter | Default | Why it's a hard default |
|---|---|---|
| `network` | `"none"` | No egress unless explicit. |
| `user` | `"65534:65534"` (nobody) | Non-root inside the container. |
| `read_only_root` | `True` | Container rootfs is read-only. |
| `mount_readonly` | `True` | `host_workdir` is mounted read-only when supplied. |
| `mode` | `"persistent"` | One long-lived container per session. Use `"stateless"` for `docker run --rm` per call. |
| `image` | a small MS-maintained base | Override with any image that has `bash` (and `sleep` for persistent mode). |
| `approval_mode` | `"always_require"` (factory default) | Permitted to set `"never_require"` **without** `acknowledge_unsafe=True` (unlike `LocalShellTool`) because the container is the boundary. |

### `extra_run_args` is filtered

From the upstream docstring ([`_docker.py:L290-L307`](https://github.com/microsoft/agent-framework/blob/python-1.8.0/python/packages/tools/agent_framework_tools/shell/_docker.py#L290)):

> `extra_run_args` can dismantle the tool's isolation contract. Flags that would undo the default sandbox (`--privileged`, `--cap-add`, `--security-opt`, `--network`/`--net`, `-v`/`--volume`, `--mount`, `--device`, `--pid`, `--ipc`, `--userns`, `--user`, `--read-only`, `--tmpfs`, `--add-host`, `--gpus`, `--cgroupns`, `--device-cgroup-rule`) are **rejected at construction time**. Override the corresponding dedicated argument (`network`, `host_workdir`, `mount_readonly`, `read_only_root`, `user`, etc.) instead. If you genuinely need to relax the sandbox further, subclass the tool — don't slip past this check.

> [!IMPORTANT]
> The blocklist above is the **upstream rejection list**, not a complete Docker hardening policy. Common resource-limit flags that are **not** rejected (e.g. `--memory`, `--memory-swap`, `--cpus`, `--pids-limit`, `--ulimit`) still need to be set somewhere — but use the **dedicated constructor arguments** (`memory`, `pids_limit`, `network`, `user`, `read_only_root`) for sandbox-relevant settings. Reserve `extra_run_args` for benign flags (e.g. `--label`, `--name` prefixes) that don't influence isolation.

### Check Docker availability up front

```python
from agent_framework_tools.shell import is_docker_available, DockerNotAvailableError

if not is_docker_available():
    raise DockerNotAvailableError("docker / podman not on PATH or daemon not running")
```

The class can also be constructed with `docker_binary="podman"` if you prefer Podman.

---

## Decision guide: which to pick

```
Is the input from end users / web / a queue (untrusted)?
        │
        Yes
        │
        ▼
First — can this be a typed function tool instead?
(e.g. run_sql(query: str), file_read(path: str), search(q: str))
        │
        Yes ──▶ Use a normal FunctionTool. Shell is rarely needed.
        │
        No (shell genuinely required)
        │
        ▼
Threat model:
  Internal trusted users / single-tenant?
        │
        Yes ──▶ DockerShellTool(network="none", default flags) with
                approval and per-session container. Adequate.
        │
        No (adversarial / multi-tenant / supply-chain-exposed)
        │
        ▼
        DockerShellTool alone is NOT sufficient. Combine with:
          - one container per session, started fresh per request
          - strict resource limits (memory, pids_limit, timeout)
          - network="none" + outbound proxy if egress needed
          - approval/audit/quotas at the application layer
          - consider a stronger sandbox (microVM e.g. Firecracker,
            gVisor, Kata) or a separate execution service.

Trusted input — coding assistant, internal dev workflow?
        │
        ▼
Need filesystem effects on host?
        │
        No ──▶ Hosted shell (Section 1) — zero local exec.
        │
        Yes ─▶ LocalShellTool + approval_mode="always_require"
               + host approval logic.
        │
        Want auto-approve in CI / batch?
        │
        ▼
        LocalShellTool + ShellPolicy(allowlist=[strict regexes])
                       + approval_mode="never_require"
                       + acknowledge_unsafe=True
                       + mode="stateless" (preferred)
                       — only inside a CI runner you already own.
```

**The general rule (echoed in the upstream samples):** prefer a typed function tool over a shell tool when the schema is known. A `run_sql(query: str) -> list[dict]` function gives the model and you stronger guarantees than `cat /tmp/data.csv | sqlite3 …` ever will.

---

## Common mistakes

| Mistake | Fix |
|---|---|
| `from agent_framework.tools.shell import ShellTool` | The class is named `LocalShellTool` and lives in `agent_framework_tools.shell` (the `agent-framework-tools` wheel — separate `pip install`). There is no `ShellTool` class. |
| `client.get_shell_tool(mode="local")` / `mode="docker"` | `get_shell_tool` has **no** `mode` parameter. `func=None` → hosted; `func=<callable>` → local. For Docker, pass `func=DockerShellTool(...).as_function()`. |
| Passing `image=`, `network=`, `memory_limit=` to `get_shell_tool` | Those are `DockerShellTool.__init__` parameters. Construct the `DockerShellTool`, then pass `func=tool.as_function()`. |
| `LocalShellTool(allowed_commands=[...], denied_commands=[...])` | Real API: `policy=ShellPolicy(allowlist=[regex, ...], denylist=[regex, ...])`. Patterns are regex, not literal command names. |
| `approval_mode="never_require"` without `acknowledge_unsafe=True` on `LocalShellTool` | Raises `ValueError` at construction with explicit hazard text. Either keep approval or accept the risk explicitly. |
| Sharing a persistent `LocalShellTool` across users / sessions / concurrent agents | Persistent mode owns the shell process (cwd, env, history all shared). One instance per session — or use `mode="stateless"`. |
| Treating `ShellPolicy` as a security boundary | It's a **UX pre-filter**. The hard boundaries are: approval enforcement in the host app, Docker isolation, OS-level sandboxing, container `network="none"`. |
| Forgetting `async with shell:` and never calling `await shell.close()` | The persistent shell subprocess (and Docker container) leak past the end of your program. Always `async with` or call `await shell.close()`. |
| Omitting `psutil` from your dependency lock | `psutil` is a hard dep of `agent-framework-tools`; it's not optional. On Windows, process-tree termination on timeout depends on it. |
| Loose pin like `agent-framework-tools>=1.0.0a` | This is **alpha** — pin the exact version: `agent-framework-tools==1.0.0a260424`. |

---

## See also

* [`feature-stages.md`](feature-stages.md) — why `LocalShellTool` is **alpha-staged** (package version) but **not** `@experimental`-decorated, and why the warning recipes there don't apply here.
* [`tools-hosted.md`](tools-hosted.md) — Foundry hosted-tool factories (Code Interpreter, File Search, Bing grounding).
* [`tools-function.md`](tools-function.md) — typed Python function tools (often the better alternative).
* [`packages.md`](packages.md) — `agent-framework-tools` package details and version-pinning guidance.
* Upstream samples: [`02-agents/tools/`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/02-agents/tools), [`02-agents/providers/openai/`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/samples/02-agents/providers/openai)
* Upstream source: [`agent_framework_tools/shell/`](https://github.com/microsoft/agent-framework/tree/python-1.8.0/python/packages/tools/agent_framework_tools/shell)
* Original PR: [microsoft/agent-framework#5664](https://github.com/microsoft/agent-framework/pull/5664)
