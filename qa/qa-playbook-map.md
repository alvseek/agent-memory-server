# QA Playbook Map — agent-memory-server

> Navigation audit; last scan 2026-11-09. Materials stay in place. Prior Notes are copied verbatim and describe the earlier scan, not a new runtime claim.

**Category status**: exists-documented
**Owner**: /build-qa-bench

## Found

| Material | Location | Grade | Notes (prior annotations retained verbatim where present) |
|---|---|---|---|
| compose.yaml | [../compose.yaml](../compose.yaml) | exists-documented |  |
| docs/flows/awaken-db.md | [../docs/flows/awaken-db.md](../docs/flows/awaken-db.md) | exists-tribal | End-to-end trace of one flow with a sequence diagram; playbook-shaped, not in `qa/` |
| System architecture + topology | `[AGENT-MEMORY-PATH]/docs/architecture/memory-mcp-server.md` | historical / unresolved | Carries the connection map, the three-layer topology and both caller paths — real playbook content, living in the **private store** rather than in `qa/`, so a newcomer to this repo will not find it |

## Gaps

No dedicated QA playbook was found. There is one serving app; content submodule tools are not a second running service. External private-store locations above remain unresolved in this checkout.
