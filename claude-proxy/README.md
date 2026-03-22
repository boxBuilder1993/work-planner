# Claude Proxy

Local proxy server that runs Claude Code in headless mode using your Mac's subscription. The ai-poller on Railway calls this proxy through a Cloudflare Tunnel.

## Prerequisites

- `uv` — `brew install uv`
- `cloudflared` — `brew install cloudflared`
- `claude` — Claude Code CLI, authenticated (`claude auth status` should show logged in)

## First-time setup

1. Login to Cloudflare (one-time):
   ```bash
   cloudflared tunnel login
   ```
   Select `shravan-box-builder.net` in the browser.

2. The tunnel `ai` (ID: `ea2c0844-e1eb-446d-b2ba-c51d6687e853`) is already created with a route:
   - `claude-proxy.shravan-box-builder.net` → `localhost:8400`

## Starting the proxy

Every time you want agents to run, open two terminals:

**Terminal 1 — Cloudflare Tunnel:**
```bash
cloudflared tunnel run ai
```

**Terminal 2 — Proxy Server:**
```bash
cd ~/BoxBuilderProjects/WorkPlanner/claude-proxy
CLAUDE_PROXY_KEY=workplanner-proxy-2026 uv run proxy.py
```

## Verify it's working

```bash
# Local check
curl http://localhost:8400/health

# Through tunnel
curl https://claude-proxy.shravan-box-builder.net/health
```

Should return `{"status":"ok","auth":{"loggedIn":true,...}}`.

## Stopping

Ctrl+C in both terminals. Agents will stop spawning until you restart.

## Notes

- Your Mac must be awake and connected to the internet for agents to run.
- Max 3 concurrent agent runs (hardcoded semaphore in proxy).
- Claude Max subscription is used — no API key costs.
- The proxy key (`CLAUDE_PROXY_KEY`) is set on Railway's ai-poller service.
