#!/usr/bin/env bash
# start-all.sh — bring up the local dev stack with one command.
#
# - claude-proxy runs on the Mac (uses your claude.ai subscription).
#   Skipped if it's already serving on :8400.
# - docker compose brings up postgres, chromadb, backend, ai-poller, web.
#   `docker compose up` is idempotent — already-running containers stay,
#   exited ones get recreated, code changes get rebuilt with --build.
#
# Usage:
#   ./start-all.sh             # start everything (default)
#   ./start-all.sh --no-build  # skip the docker rebuild
#   ./start-all.sh --logs      # tail compose logs after starting
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
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD_FLAG="" ;;
    --logs)     TAIL_LOGS=1 ;;
    *)
      echo "unknown arg: $arg"; exit 2 ;;
  esac
done

# ── Pre-flight ────────────────────────────────────────────────────────────

if [ ! -f .env ]; then
  echo "❌ .env missing. Copy from .env.example and set JWT_SECRET + INTERNAL_API_KEY:"
  echo "     cp .env.example .env"
  echo "     openssl rand -hex 32  # use for JWT_SECRET and INTERNAL_API_KEY"
  exit 1
fi

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
