# Claude Proxy

Local proxy server that runs Claude Code in headless mode using your Mac's subscription. The ai-poller on Railway calls this proxy through a Cloudflare Tunnel.

## Architecture

```
Railway ai-poller
    ↓ POST /run (HTTPS)
claude-proxy.shravan-box-builder.net
    ↓ Cloudflare Tunnel
Your Mac (localhost:8400)
    ↓ proxy.py (FastAPI)
claude -p (Claude Code CLI, headless mode)
    ↓ MCP servers (launched automatically per run)
    ├── workplanner_server.py → Railway backend API
    └── algo_server.py → Railway backend API (state transitions)
```

## Components

| Component | What it does | Where it runs |
|-----------|-------------|---------------|
| `proxy.py` | FastAPI server, accepts `/run` requests, spawns `claude -p` | Your Mac, port 8400 |
| `workplanner_server.py` | MCP server for task/comment tools | Your Mac (launched by `claude -p`) |
| `algo_server.py` | MCP server for state transition tools | Your Mac (launched by `claude -p`) |
| `api_client.py` | HTTP client for Railway backend | Used by MCP servers |
| Cloudflare Tunnel | Routes internet traffic to localhost | Your Mac (`cloudflared`) |

MCP servers are **not started manually** — the proxy generates an MCP config file per request and `claude -p` launches them as subprocesses automatically.

## Prerequisites

Install these on your Mac:

```bash
# uv — Python package manager
brew install uv

# cloudflared — Cloudflare Tunnel connector
brew install cloudflared

# Claude Code CLI (should already be installed)
claude --version

# Verify Claude is authenticated
claude auth status
# Should show: loggedIn: true, subscriptionType: max

# wp CLI — personas run `wp knowledge search` for KB due diligence.
# Must be on PATH wherever the proxy spawns claude -p (i.e. this host).
make -C .. install-cli        # pipx install ./cli  → puts `wp` on PATH
wp --version
```

The proxy injects `WP_BASE_URL` / `WP_INTERNAL_KEY` (from its own
`WORKPLANNER_API_URL` / `INTERNAL_API_KEY`) into the `claude -p` environment,
so `wp knowledge` authenticates with no config file. If `wp` isn't on PATH,
personas simply can't do KB lookups — dispatches still run, just without
knowledge-card grounding.

## First-time setup

### 1. Cloudflare login (one-time)

```bash
cloudflared tunnel login
```

Select `shravan-box-builder.net` in the browser when prompted.

### 2. Tunnel configuration

The tunnel `ai` is already created:
- **Tunnel ID**: `ea2c0844-e1eb-446d-b2ba-c51d6687e853`
- **Route**: `claude-proxy.shravan-box-builder.net` → `localhost:8400`
- **Dashboard**: https://dash.cloudflare.com/tunnels/ea2c0844-e1eb-446d-b2ba-c51d6687e853

### 3. Railway env vars (already set)

```
CLAUDE_PROXY_URL=https://claude-proxy.shravan-box-builder.net
CLAUDE_PROXY_KEY=workplanner-proxy-2026
```

## Starting everything

Open two terminals:

### Terminal 1 — Cloudflare Tunnel

```bash
cloudflared tunnel run ai
```

Keep this running. It connects your Mac to Cloudflare's network.

### Terminal 2 — Proxy Server

```bash
cd ~/BoxBuilderProjects/WorkPlanner/claude-proxy
CLAUDE_PROXY_KEY=workplanner-proxy-2026 uv run proxy.py
```

On first run, `uv` will create a virtual environment and install dependencies automatically.

## Verify everything works

```bash
# 1. Check proxy is running locally
curl http://localhost:8400/health

# 2. Check tunnel is routing
curl https://claude-proxy.shravan-box-builder.net/health

# Both should return:
# {"status":"ok","auth":{"loggedIn":true,"subscriptionType":"max",...}}

# 3. Check Railway can reach the proxy (from poller logs)
railway logs --service ai-poller | grep "proxy"
```

## Stopping

Ctrl+C in both terminals. The ai-poller will log errors when it can't reach the proxy, but will retry on the next cycle. No data is lost — tasks stay in their current state.

## Troubleshooting

### Proxy won't start
```bash
# Check if port is already in use
lsof -i :8400

# Kill existing process
kill $(lsof -ti :8400)

# Restart
CLAUDE_PROXY_KEY=workplanner-proxy-2026 uv run proxy.py
```

### Tunnel not connecting
```bash
# Check tunnel status
cloudflared tunnel info ai

# Re-login if cert expired
cloudflared tunnel login
```

### Claude auth expired
```bash
# Check auth
claude auth status

# Re-login
claude auth login
```

### MCP server errors
MCP servers are launched by `claude -p` per request. Check proxy logs for errors. The servers need these env vars (set automatically by the proxy):
- `WORKPLANNER_API_URL` — Railway backend URL
- `INTERNAL_API_KEY` — backend auth key
- `ALGO_TASK_ID` — task being processed (algo server only)
- `ALGO_AI_STATUS` — current task phase (algo server only)
- `ALGO_TOOLS` — enabled tools for this phase (algo server only)

## Notes

- Your Mac must be **awake and online** for agents to run.
- Max **3 concurrent** agent runs (semaphore in proxy.py).
- Uses **Claude Sonnet 4.6** via your Max subscription — no API costs.
- The proxy key prevents unauthorized access through the tunnel.
- Each `claude -p` run gets its own MCP config file (auto-cleaned up).
