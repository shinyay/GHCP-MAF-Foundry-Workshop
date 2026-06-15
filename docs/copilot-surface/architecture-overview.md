# Copilot Surface Architecture Overview

> [!NOTE]
> This document explains how the **25 Copilot-facing components** in `.github/` interact:
> 17 prompts + 3 skills + 4 chatmodes + 4 instructions, plus the 82-entry knowledge base
> in `kb-1.8.0/` and the 5 starter templates in `templates/`.

## Who is this for?

- Developers extending the template who want to know **where to add a new prompt vs chatmode vs skill**
- Reviewers evaluating the template who want a **system-level mental model**
- New contributors trying to find **which file does what**

## The 5 Copilot surface element types

```mermaid
classDiagram
    class Instruction {
        +applyTo: glob pattern
        +Auto-applied to matching files
        +Examples: python.instructions.md, infra.instructions.md
    }
    class Prompt {
        +name, tier, hand_off_target
        +Invoked explicitly by user
        +Single-task scope
        +18 total
    }
    class Skill {
        +trigger phrases, activation fixtures
        +Auto-activated based on intent
        +Composite (calls multiple prompts/agents)
        +3 total
    }
    class Chatmode {
        +description, tools allowlist
        +Switches user persona
        +Multi-turn conversation
        +4 total (af-architect, af-implementer, af-reviewer, foundry-ops)
    }
    class KB {
        +patterns (30), anti-patterns (17)
        +api-reference (31), migration-guides (4)
        +Cited by prompts/chatmodes/skills
        +Read-only reference
    }
    Chatmode --> Prompt : invokes
    Chatmode --> KB : cites
    Skill --> Prompt : composes
    Skill --> Chatmode : delegates to
    Prompt --> Chatmode : hands off to
    Prompt --> KB : cites
    Instruction --> Chatmode : provides guardrails
```

## How a user interaction flows

```mermaid
sequenceDiagram
    participant U as User in VS Code
    participant C as GitHub Copilot
    participant CM as Chatmode (e.g., af-implementer)
    participant P as Prompt (e.g., add-tool)
    participant KB as KB (e.g., canonical-agent-creation.md)
    participant FO as foundry-ops chatmode (if escalated)
    
    U->>C: "Add a stock price tool to my agent"
    C->>CM: Switch to af-implementer
    CM->>P: Invoke add-tool.prompt.md
    P->>KB: Read patterns/canonical-agent-creation.md
    P->>U: Emit scaffolded code + diff
    U->>C: "Now deploy to Foundry"
    C->>FO: Escalate to foundry-ops
    FO->>KB: Read api-reference/1.8.0/hosted-agent-deploy.md
    FO->>U: Emit safety-tagged azd commands
    U->>U: Review + execute manually
```

## Chatmode hand-off matrix

The 4 chatmodes are NOT independent — they hand off via a documented matrix to keep
responsibilities clean.

```mermaid
graph LR
    USER([User direct])
    AR[af-architect<br/>Pre-impl design]
    AI[af-implementer<br/>Code generation]
    REV[af-reviewer<br/>Post-impl review]
    FO[foundry-ops<br/>Env + Azure CLI]
    
    USER --> AR
    USER --> AI
    USER --> REV
    USER --> FO
    
    AR -->|"design done<br/>→ implement"| AI
    AI -->|"code done<br/>→ review"| REV
    REV -->|"changes needed<br/>→ re-implement"| AI
    AI -->|"env error<br/>→ triage"| FO
    REV -->|"env error<br/>→ triage"| FO
    FO -.->|"returns control<br/>(never hand-off downstream)"| USER
    
    style AR fill:#cce5ff
    style AI fill:#ffeebb
    style REV fill:#ccffcc
    style FO fill:#ffcccc
```

> [!IMPORTANT]
> **`foundry-ops` is special**: it never hands off downstream. It always returns control to
> the originating chatmode (or user). This is the **R-PHASE3-RISK-1 safety boundary** —
> environment ops are read+search only, never execute.

## Prompt invocation flow

```mermaid
flowchart TD
    Start([User asks Copilot]) --> Detect{Intent matches<br/>a skill trigger?}
    Detect -->|YES| Skill[Skill auto-activates<br/>e.g., foundry-bootstrap]
    Detect -->|NO| Direct{User invokes<br/>prompt explicitly?}
    Skill --> Compose[Skill composes:<br/>provision-foundry + deploy-agent-to-foundry + foundry-ops]
    Direct -->|YES| Prompt[Run prompt.md<br/>e.g., add-tool]
    Direct -->|NO| Chatmode[User uses<br/>chatmode chat]
    Compose --> Plan[Emit ordered plan]
    Prompt --> Plan
    Chatmode --> Plan
    Plan --> Verify[Plan + verify gates]
    Verify --> Handoff[Hand-off per matrix]
    
    style Skill fill:#cce5ff
    style Compose fill:#cce5ff
```

## Safety boundaries (R-PHASE3-RISK-1)

```mermaid
graph TB
    subgraph Execute_Capable["Execute-capable chatmodes / prompts"]
        AI[af-implementer]
        REV[af-reviewer]
    end
    subgraph Read_Only_Safe["READ + SEARCH only"]
        FO[foundry-ops]
        FB[foundry-bootstrap skill]
        AK[af-knowledge skill]
        RR[review-report-format skill]
    end
    subgraph KB_Source["KB documentation"]
        K[kb-1.8.0/* 82 entries]
    end
    
    AI -.->|"never bypass<br/>foundry-ops safety"| FO
    REV -.->|"never bypass"| FO
    FO --> K
    FB --> K
    AK --> K
    RR --> K
    
    style Execute_Capable fill:#ffeecc
    style Read_Only_Safe fill:#ccffcc
```

**Key rule**: `foundry-ops` emits `az` commands as **conversational markdown**, never
executes them. Composite skills inherit this boundary.

## Instructions (auto-applied guardrails)

The 4 `.github/instructions/*.md` files are auto-applied by Copilot to files matching
their `applyTo` glob:

| File | applyTo | Purpose |
|---|---|---|
| `python.instructions.md` | `**/*.py` | Python coding conventions (typing, structure, AGENTS.md alignment) |
| `tests.instructions.md` | `**/tests/**/*.py` | Test-specific conventions (AST parity, pytest patterns) |
| `infra.instructions.md` | `**/*.bicep,**/azure.yaml,**/main.parameters.json` | Bicep RBAC patterns, az CLI vs azd traps, principalType conventions |
| `docs.instructions.md` | `**/*.md` | Markdown style + frontmatter requirements |

These are **transparent** to the user — Copilot consults them automatically when editing
matching files. No explicit invocation needed.

## KB anatomy

```mermaid
graph LR
    KB[kb-1.8.0/]
    KB --> P[patterns/<br/>30 entries<br/>How to do things]
    KB --> AP[anti-patterns/<br/>17 entries<br/>What to avoid]
    KB --> API[api-reference/1.8.0/<br/>31 entries<br/>What the API does]
    KB --> MG[migration-guides/<br/>4 entries<br/>How to upgrade]
    
    P -.->|"cited by"| Prompts
    AP -.->|"cited by"| Triage
    API -.->|"cited by"| AllSurfaces
    MG -.->|"cited by"| Upgrade
    
    Prompts[17 prompts]
    Triage[foundry-ops Triage Catalogue]
    AllSurfaces[All surface elements]
    Upgrade[upgrade-version + migrate-* prompts]
```

## When to add what

| You want to… | Add a… | Example |
|---|---|---|
| Provide a one-shot capability to users | **Prompt** | `add-stripe-payments.prompt.md` |
| Compose multiple capabilities for a common flow | **Skill** | `setup-payment-stack` (composes `add-stripe` + `add-vat` + `deploy-checkout`) |
| Provide a specialist persona for a domain | **Chatmode** | `db-ops.agent.md` for database admin work |
| Auto-apply rules to file types | **Instruction** | `terraform.instructions.md` for `.tf` files |
| Document a working pattern | **KB pattern** | `kb-1.8.0/patterns/payment-webhook-handling.md` |
| Document a known failure mode | **KB anti-pattern** | `kb-1.8.0/anti-patterns/stripe-webhook-replay-attack.md` |

## See also

- [`./prompt-catalog.md`](./prompt-catalog.md) — all 17 prompts × purpose / when / inputs / hand-off
- [`./skill-catalog.md`](./skill-catalog.md) — all 3 skills × triggers + composite workflow
- [`./agent-catalog.md`](./agent-catalog.md) — all 4 chatmodes × objectives + safety
- [`./scenarios.md`](./scenarios.md) — all 5 starters × usage scenarios
- [`./template-design-principles.md`](./template-design-principles.md) — meta design rules
- [`../CHANGELOG.md`](../CHANGELOG.md) — recent changes
