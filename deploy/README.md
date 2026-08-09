# Deploy — Munnin on RackNerd

**systemd + uv, no Docker.** Munnin binds loopback `127.0.0.1:8200`; agents reach it via an **SSH tunnel**. `MemoryMax=200M`.

## Files
- `munnin.service` — systemd unit (installed to `/etc/systemd/system/`)
- `deploy.sh` — rsync source → box, `uv sync`, install unit, restart
- `restart.sh` — restart the service
- `deploy.env.example` → copy to `deploy.env` (gitignored) — LOCAL deploy config (host, path, ssh key)
- `munnin.env.example` → copy to `munnin.env` (gitignored) — REMOTE runtime env (systemd `EnvironmentFile`)
- `mcp.json.example` — MCP client entry pointing at the tunneled endpoint

## One-time box setup (Phase 8)
1. `deploy` user + `uv` installed (Ubuntu 24.04 has no `python3-venv` → uv required)
2. Place `deploy/munnin.env` on the box
3. NOPASSWD sudo for: `systemctl daemon-reload`, `enable munnin`, `restart munnin`, `status munnin` (exact-argv match — grant each form)

## Deploy
```bash
cp deploy/deploy.env.example deploy/deploy.env   # fill in
bash deploy/deploy.sh
```

## Connect from your machine (SSH tunnel)
```bash
ssh -N -L 8200:127.0.0.1:8200 deploy@<racknerd-host> -i ~/.ssh/<key>
```
Then use `mcp.json.example` (points at `http://localhost:8200/mcp/`, forwarded to the box).
