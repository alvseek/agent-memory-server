# Munnin — Required Config Inventory

> Every config key the system needs to start. Munnin is local-first with **no secrets** — every key is defaulted in `munnin.configuration.config`. Override via `MUNNIN_*` env vars only when you need non-defaults.

| Key | Used by | Status | Acquisition step / source |
|---|---|---|---|
| `MUNNIN_HOST` | server bind | exists & documented | default `127.0.0.1` |
| `MUNNIN_PORT` | server bind | exists & documented | default `8200` |
| `MUNNIN_USER_ID` | tenancy (stamped server-side) | exists & documented | default `alvi` |
| `MUNNIN_DB_PATH` | SQLite store | exists & documented | default `data/valaskjalf-memory.db` (gitignored) |
| `MUNNIN_CONTENT_ROOT` | served content (prompts/resources) | exists & documented | default `control-files` (submodule) |
| `MUNNIN_IMPORT_SOURCE` | importer seed source | exists & documented | default `~/.claude/@agent-memory` (the real markdown tree) |

## Acquisition Notes
- **No secrets, no external accounts.** v1 is single-tenant local-first and ships no auth; a real deployment is expected to sit behind a reverse proxy or tunnel.
- The only real precondition is that `MUNNIN_IMPORT_SOURCE` points at a valid markdown memory tree and the `control-files` submodule is checked out.
