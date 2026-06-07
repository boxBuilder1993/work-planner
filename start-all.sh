#!/usr/bin/env bash
# start-all.sh — bring up the local dev stack with one command.
#
# - claude-proxy runs on the Mac (uses your claude.ai subscription).
#   Skipped if it's already serving on :8400.
# - docker compose brings up postgres, backend, ai-poller, web.
#   `docker compose up` is idempotent — already-running containers stay,
#   exited ones get recreated, code changes get rebuilt with --build.
#
# Usage:
#   ./start-all.sh             # start everything (default)
#   ./start-all.sh --no-build  # skip the docker rebuild
#   ./start-all.sh --logs      # tail compose logs after starting
#   ./start-all.sh --env-only  # just bootstrap .env (if missing) and exit
#
# On first run with no .env, this bootstraps one from .env.example with freshly
# generated JWT_SECRET + INTERNAL_API_KEY — so a fresh checkout (dev or a
# company laptop) needs nothing but Docker + uv.
#
# Stop with:
#   docker compose down        # stop the stack (keeps data)
#   kill $(cat .claude-proxy.pid)  # stop the proxy if you started it via this script

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

PROXY_URL="http://localhost:8400"
PROXY_LOG="$REPO_ROOT/.claude-proxy.log"
PROXY_PID_FILE="$REPO_ROOT/.claude-proxy.pid"

BUILD_FLAG="--build"
TAIL_LOGS=0
ENV_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD_FLAG="" ;;
    --logs)     TAIL_LOGS=1 ;;
    --env-only) ENV_ONLY=1 ;;
    *)
      echo "unknown arg: $arg"; exit 2 ;;
  esac
done

# ── .env bootstrap ─────────────────────────────────────────────────────────
# Create .env on first run so a fresh checkout is one command. Never touches an
# existing .env — your secrets are preserved.

if [ ! -f .env ]; then
  if [ ! -f .env.example ]; then
    echo "❌ neither .env nor .env.example present; cannot bootstrap."
    exit 1
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "❌ openssl not found — needed to generate secrets. Install it and retry."
    exit 1
  fi
  echo "→ no .env found — creating one from .env.example with generated secrets …"
  cp .env.example .env
  jwt_value="$(openssl rand -hex 32)"
  int_value="$(openssl rand -hex 32)"
  # hex values are regex-safe (no /), so plain s/// is fine.
  perl -pi -e "s/^JWT_SECRET=.*/JWT_SECRET=${jwt_value}/; s/^INTERNAL_API_KEY=.*/INTERNAL_API_KEY=${int_value}/" .env
  echo "✓ .env created with random JWT_SECRET + INTERNAL_API_KEY."
else
  [ "$ENV_ONLY" -eq 1 ] && echo "✓ .env already present — leaving it alone."
fi

if [ "$ENV_ONLY" -eq 1 ]; then
  exit 0
fi

# ── Pre-flight ────────────────────────────────────────────────────────────

if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv not found. Install: brew install uv"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker daemon not running. Start Docker Desktop and retry."
  exit 1
fi

# ── claude-proxy ──────────────────────────────────────────────────────────

if curl -s -m 2 "$PROXY_URL/health" 2>/dev/null | grep -q '"status":"ok"'; then
  echo "✓ claude-proxy already running on :8400 — leaving it alone."
else
  echo "→ starting claude-proxy in background (logs: $PROXY_LOG) …"

  # The proxy reads WORKPLANNER_API_URL + INTERNAL_API_KEY straight from its
  # own env (no .env loader) and refuses to serve MCP/wp calls without them.
  # For a local run, point it at the host-published backend (docker maps
  # 8080:8080) and reuse the key from .env. Anything already exported — e.g. a
  # prod-pointed proxy on your personal Mac — is respected, not overridden.
  : "${WORKPLANNER_API_URL:=http://localhost:8080}"
  if [ -z "${INTERNAL_API_KEY:-}" ]; then
    INTERNAL_API_KEY="$(grep -E '^INTERNAL_API_KEY=' "$REPO_ROOT/.env" | head -1 | cut -d= -f2-)"
    INTERNAL_API_KEY="${INTERNAL_API_KEY%\"}"; INTERNAL_API_KEY="${INTERNAL_API_KEY#\"}"
    INTERNAL_API_KEY="$(printf '%s' "$INTERNAL_API_KEY" | tr -d '[:space:]')"
  fi
  if [ -z "$INTERNAL_API_KEY" ]; then
    echo "❌ INTERNAL_API_KEY not found in .env or environment — the proxy would"
    echo "   reject every MCP/wp call (so the archivist and @ai would do nothing)."
    exit 1
  fi
  export WORKPLANNER_API_URL INTERNAL_API_KEY
  echo "  proxy → backend at $WORKPLANNER_API_URL"

  cd "$REPO_ROOT/claude-proxy"
  nohup uv run python proxy.py > "$PROXY_LOG" 2>&1 &
  echo $! > "$PROXY_PID_FILE"
  cd "$REPO_ROOT"

  # Wait up to 30s for it to come up.
  for _ in $(seq 1 30); do
    if curl -s -m 1 "$PROXY_URL/health" 2>/dev/null | grep -q '"status":"ok"'; then
      echo "✓ claude-proxy ready  (pid $(cat "$PROXY_PID_FILE"))"
      break
    fi
    sleep 1
  done

  if ! curl -s -m 1 "$PROXY_URL/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "❌ claude-proxy didn't come up. Last 30 log lines:"
    tail -30 "$PROXY_LOG" || true
    exit 1
  fi
fi

# ── docker compose ────────────────────────────────────────────────────────

echo "→ docker compose up $BUILD_FLAG -d …"
# shellcheck disable=SC2086
docker compose up $BUILD_FLAG -d

echo
echo "✓ stack up:"
docker compose ps --format "  {{.Service}}\t{{.Status}}"
echo
echo "Open:  http://localhost:3000   (frontend, sign in with email in dev)"
echo "Stop:  docker compose down"

if [ "$TAIL_LOGS" -eq 1 ]; then
  echo
  echo "→ tailing logs (Ctrl-C to detach; stack keeps running) …"
  docker compose logs -f --tail=50
fi
