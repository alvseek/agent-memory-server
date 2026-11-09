# QA Config Map — agent-memory-server

> Navigation audit; last scan 2026-11-09. Materials stay in place. Prior Notes are copied verbatim and describe the earlier scan, not a new runtime claim.

**Category status**: exists-documented
**Owner**: /build-qa-bench

## Found

| Material | Location | Grade | Notes (prior annotations retained verbatim where present) |
|---|---|---|---|
| .env.example | [../../.env.example](../../.env.example) | exists-documented | The committed shape of every `MUNNIN_*` setting; not part of the QA loop's config, listed for completeness |
| compose.yaml | [../../compose.yaml](../../compose.yaml) | exists-documented |  |
| qa/config/.env.local.template | [.env.local.template](.env.local.template) | exists-documented | Placeholders only |
| qa/config/REQUIRED.md | [REQUIRED.md](REQUIRED.md) | exists-documented | In the canonical home under its canonical name |
| src/munnin/configuration/config.py | [../../src/munnin/configuration/config.py](../../src/munnin/configuration/config.py) | exists-documented | `MUNNIN_*` env vars with working defaults — the reason this project needs almost no config to start |

## Gaps

No new material built by this audit. Discovery/link resolution is not runtime verification. The four bench phases remain linked and documented.
