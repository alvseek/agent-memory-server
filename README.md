# Munnin — an agent identity server

Munnin gives an AI agent a persistent self — identity, reasoning patterns, emotional moments, episodic history, knowledge — and serves the **procedures for tending that memory** beside the data, over MCP. It is the memory server of the [agent-memory framework](https://github.com/alvseek/agent-memory-system): an agent awakens from it as *who it is*, not from a pile of recalled facts, and writes back through the same discipline.

Python · FastMCP · FastAPI · SQLite. Apache-2.0. Runs on a laptop in five minutes with no identity provider.

## Five-minute run

Needs Docker and git.

```sh
git clone --recurse-submodules https://github.com/alvseek/agent-memory-server
cd agent-memory-server
docker compose up -d --build
curl http://127.0.0.1:8200/health      # {"status":"ok","service":"munnin","version":"0.1.0"}
```

Connect a client. Claude Code:

```sh
claude mcp add --transport http munnin http://127.0.0.1:8200/mcp
```

or in a project's `.mcp.json`:

```json
{ "mcpServers": { "munnin": { "type": "http", "url": "http://127.0.0.1:8200/mcp" } } }
```

Then, in a session: `ping` answers `pong`, `list_procedures` returns the 13 memory procedures, and `read_procedure("create-agent")` walks you through making the first agent. No sign-in happens: this is **local mode** — one tenant, reachable from this machine only, and the server refuses to start any other way ([how that guard works](docs/README.md#local-mode)).

No Docker? `uv sync && MUNNIN_AUTH=off uv run python -m munnin` does the same on `127.0.0.1:8200`.

## Hosting it

The default is **token mode**: every `/mcp` and `/api` call needs a bearer token from an OIDC issuer that binds tokens to this server (`aud` = `https://<your-host>/mcp`), and each person who signs in gets their own tenant. Set `MUNNIN_PUBLIC_BASE_URL` and `MUNNIN_LOGTO_ENDPOINT`, put it behind TLS, and paste `https://<your-host>/mcp` into claude.ai's connectors or `claude mcp add`. The issuer requirements, the one-identifier rule, and the prebuilt image are in [How Is It Deployed](docs/README.md#how-is-it-deployed).

## Develop

```sh
uv sync
uv run pytest        # 446 tests
uv run ruff check
```

Full architecture, the tool and endpoint surface, the data model, and known debts: [docs/README.md](docs/README.md).

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Alviandi Widiasto. The `control-files` submodule ([agent-memory-system](https://github.com/alvseek/agent-memory-system)) is licensed the same way, so a clone with submodules is one licence throughout.
