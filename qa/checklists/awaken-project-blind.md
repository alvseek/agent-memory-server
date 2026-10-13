# Awaken Goes Project-Blind — QA Checklist

**Source**: [plans/2026-10-13-agent-memory-server-awaken-project-blind.md](../../plans/2026-10-13-agent-memory-server-awaken-project-blind.md)
**Purpose**: confirm that `awaken` returns a complete, correctly-ordered payload with no project in its contract, and that the caller's new obligation (select the episode yourself) actually resolves — for a project whose own newest episode is *not* the newest overall.
**Apps under test**: `munnin` (service + MCP face + HTTP face) and the served procedure text in `control-files`. Deliberately NOT touched: the repository's `project` filter, the corpus boundary, the coding-reasoning lane, the overlay's procedures, and anything in `hermod-server`.

## Terminology & state model (read first)

- **Project-blind** — the tool takes a domain and returns the memory set. It accepts no project, resolves none, and returns no project-scoped choice. This is the state the change created.
- **`latest_episode`** — now simply the newest episode *overall*, by `(created_date, id)` descending. It is not "yours", and it usually belongs to another project.
- **Caller-side selection** — a caller that needs its own project's episode reads `episodic_index`, finds the newest entry whose `project` matches, and fetches the body with `get(uuid)`. That obligation moved from the server to the caller.

**Key invariants** (each is a thing to *disprove*):

- A chat consumer's payload shape is unchanged: the same top-level keys, each keeping its inner shape, so a layer-rendering consumer (telegent's brain, `universal-chat-agent`) produces the same prompt it did before.
- Every `episodic_index` entry still carries `project`, so selection remains possible.
- The caller's new path terminates: a project whose own newest episode is not the newest overall can still obtain that episode's body.
- No unit test in the suite can fail if `project` is added back to the tool: an undeclared argument is ignored, so a re-added parameter leaves every test green. The removal is therefore verifiable only against the live schema and the served text.

## Happy path — single end-to-end scenario (run this first)

1. Start the stack (`qa/scripts/start-server.sh` after `reset-db.sh` + `seed-meta.sh`), then call the MCP tool `awaken(domain="meta")`. See [§ Payload](#payload-shape-and-order).
2. Take `latest_episode.project` from that payload, then find a project in `episodic_index` that has its own newest episode and is *not* that project. Fetch it with `get(uuid)`. See [§ Caller-side selection](#caller-side-selection).
3. Read the served `awaken-agent` procedure and confirm it carries no project instruction. See [§ Served text](#served-text).
4. Call `awaken` with a project argument anyway and confirm it is accepted and ignored, on both transports. See [§ Tolerance](#tolerance-of-a-stale-caller).

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| `latest_episode` is the newest overall even with several projects present | `tests/business_services/test_awaken.py::test_awaken_latest_episode_is_the_newest_overall` | — |
| `episodic_index` entries still carry `project` | `tests/business_services/test_awaken.py::test_awaken_index_entries_carry_project` | — |
| A project-keyed episode stays readable (the column survives) | `tests/data_repositories/test_repository_contract.py::test_a_project_keyed_episode_is_still_readable` | — |
| Both faces still serve a payload for a valid domain, and 400 on an invalid one | `tests/api_http/test_awaken_faces.py` | — |
| The coding lane still stays out of the payload | `tests/test_fidelity.py` | — |
| **The tool declares no `project`** | none can: a re-added parameter would pass every one of the above, because an undeclared argument is ignored | **inspecting the live tool schema and the served text** |
| The payload's key set is unchanged for a chat consumer | none asserts top-level keys as a contract | **comparing key sets against a pre-change payload or the consumer's renderer** |
| A caller can still reach a non-newest project's episode body | none exercises `get(uuid)` as the fallback path | **the whole of § Caller-side selection** |

## Checks

### Payload shape and order
- [ ] `awaken("meta")` returns exactly these top-level keys: `agent_id`, `shared`, `identity`, `reasoning`, `emotional`, `knowledge_index`, `episodic_index`, `latest_episode`. Expect: identical set to a pre-change payload, no additions and no removals.
- [ ] `shared` still carries `reasoning`, `knowledge`, `ras`, `user_profile`, each with its previous role (whole bodies for the first three, a single record or `null` for the profile).
- [ ] `latest_episode` is the entry with the greatest `(created_date, id)` in `episodic_index`. Expect: equality on `uuid`, not merely a plausible-looking title.
- [ ] Every `episodic_index` entry has a `project` key present (its value may be `null` for the ones that predate project tagging).
- [ ] An agent with **zero** episodes returns `latest_episode: null` rather than raising. This is the path the deleted helper used to own.

### Caller-side selection
- [ ] Pick a project that has at least one episode and whose newest episode is **not** the newest overall. Confirm its newest episode appears in `episodic_index` with that `project` value.
- [ ] `get(uuid)` on that entry returns its **full body**, not an index projection. Expect: a body at least as long as the index entry's `title`, and no `project` key missing from the response.
- [ ] A coding awakening in that project names that episode as its carry-forward, and its Tech Debts and Next Steps match the body fetched in the previous step.
- [ ] Negative: with a project that has no episode at all, the caller falls back to `latest_episode`, and its report says the episode is not project-specific.

### Served text
- [ ] The served `awaken-agent` procedure contains no `awaken(domain, project)` and no `&project=`. Expect: both absent from the served text, not merely from the repository.
- [ ] The served text states that the caller selects its own episode out of the index. Expect: a sentence to that effect in `§ load-agent-memory`.
- [ ] `refresh-memory` carries the same corrected text (it shares the op). Expect: no project instruction in its served form either.

### Tolerance of a stale caller
- [ ] MCP: `awaken(domain="meta", project="hermod-deploy")` returns HTTP-equivalent success and the same `latest_episode.uuid` as without the argument. Expect: identical payload, no error.
- [ ] HTTP: `GET /api/awaken?agent_id=meta&project=hermod-deploy` returns **200**, not 422, and the same payload. FastAPI ignores unknown query parameters, so this is the expected shape, but it is the path a stale client actually takes and nobody has exercised it.
- [ ] Both APIs' live schema shows `domain`/`agent_id` only. Expect: no `project` parameter listed.

### Not touched (regression probes)
- [ ] `GET /api/awaken` still returns 400 for an invalid domain (the `ValueError` to HTTP mapping is unchanged).
- [ ] A `knowledge` row carrying a `project` is still invisible to every Munnin read (the corpus boundary), including reads that name that project.
- [ ] Coding-reasoning rows still never appear in the payload, and `coding_reasoning()` still returns 12 patterns.
- [ ] Triage: no third-party caller is broken by this. `universal-chat-agent` calls `munnin.awaken(agent_id)` and telegent's probe hits `?agent_id=` only, so both are unaffected; a caller that *did* pass a project now gets the newest overall and must be checked for a silently wrong report.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
