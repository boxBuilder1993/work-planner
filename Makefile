.PHONY: ai-ollama ai-claude dev-backend dev dev-stack dev-stack-down dev-stack-logs dev-proxy help test test-backend test-poller test-proxy test-web test-mobile test-app test-cli install-cli test-e2e-up test-e2e-down test-integration test-e2e

help:
	@echo "Local dev (Docker Compose + claude-proxy on Mac):"
	@echo "  make dev              - Start everything (proxy on Mac + Docker stack). Idempotent."
	@echo "  make dev-proxy        - Start ONLY claude-proxy on Mac (port 8400)."
	@echo "  make dev-stack        - Start ONLY the Docker stack (postgres + chromadb + backend + ai-poller + web)"
	@echo "  make dev-stack-down   - Stop the Docker stack (keeps data; doesn't touch the proxy)"
	@echo "  make dev-stack-logs   - Tail logs from all Docker services"
	@echo ""
	@echo "Legacy AI targets (Ollama / Claude direct):"
	@echo "  make ai-ollama        - Start Ollama and configure for qwen2.5:14b model"
	@echo "  make ai-claude        - Configure for Claude Haiku (requires 1Password CLI)"
	@echo "  make dev-backend      - Start backend with configured AI provider"
	@echo ""
	@echo "Test targets:"
	@echo "  make test           - Run every component's tests sequentially"
	@echo "  make test-backend   - Go backend: go vet + go build + go test"
	@echo "  make test-poller    - ai-poller: python -m unittest discover"
	@echo "  make test-proxy     - claude-proxy: uv-managed unittest discover"
	@echo "  make test-web       - web: eslint + production build (tsc -b + vite)"
	@echo "  make test-mobile    - mobile: tsc --noEmit type-check"
	@echo "  make test-app       - Android: ./gradlew test (unit tests, not APK)"

# Start Ollama and configure for qwen2.5:14b local model
.PHONY: ai-ollama
ai-ollama:
	@echo "Starting Ollama and pulling qwen2.5:14b..."
	@command -v ollama >/dev/null 2>&1 || (echo "Ollama not found. Install from https://ollama.ai"; exit 1)
	@echo "Pulling qwen2.5:14b (first run may take time)..."
	ollama pull qwen2.5:14b
	@echo "Setting environment variables..."
	$(eval export AI_MODEL=ollama/qwen2.5:14b)
	$(eval export AI_API_BASE=http://localhost:11434)
	$(eval unset AI_API_KEY)
	@echo "Ollama setup complete. AI_MODEL=ollama/qwen2.5:14b"
	@echo "Run: make dev-backend"

# Configure for Claude Haiku (requires ANTHROPIC_API_KEY from 1Password)
.PHONY: ai-claude
ai-claude:
	@echo "Setting up Claude Haiku via Anthropic API..."
	@command -v op >/dev/null 2>&1 || (echo "1Password CLI not found. Install from https://developer.1password.com/docs/cli"; exit 1)
	@echo "Fetching ANTHROPIC_API_KEY from 1Password..."
	$(eval export AI_API_KEY := $(shell op read "op://Finance Planner/Anthropic API Key/password" 2>/dev/null || echo ""))
	@if [ -z "$(AI_API_KEY)" ]; then \
		echo "❌ Could not fetch API key from 1Password. Make sure you have the 'Anthropic API Key' item in 1Password"; \
		exit 1; \
	fi
	$(eval export AI_MODEL=claude-haiku-4-5)
	$(eval unset AI_API_BASE)
	@echo "✅ Claude setup complete. AI_MODEL=claude-haiku-4-5"
	@echo "Run: make dev-backend"

# Start backend with configured AI provider
.PHONY: dev-backend
dev-backend:
	@if [ -z "$(AI_MODEL)" ]; then \
		echo "❌ AI_MODEL not set. Run: make ai-ollama  OR  make ai-claude"; \
		exit 1; \
	fi
	cd backend && python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

# ─── Local dev stack (Docker Compose) ──────────────────────────────────────
# claude-proxy runs on the Mac directly; ai-poller (in Docker) reaches it
# via http://host.docker.internal:8400 — no Cloudflare Tunnel needed.
# Set ENABLE_CHAT_HANDLER=true on ai-poller and forward WORKPLANNER_WORKSPACE_BASE
# to the host home dir so claude-proxy can mkdir there.

# One-shot: starts the proxy (if not already on :8400) and the Docker stack.
# Both are idempotent.
dev:
	./start-all.sh

# Foreground proxy (separate terminal). Use this if you want the proxy logs
# in your terminal; otherwise `make dev` handles startup in the background.
dev-proxy:
	@command -v uv >/dev/null 2>&1 || (echo "uv not found. brew install uv"; exit 1)
	cd claude-proxy && uv run python proxy.py

# Then in this terminal:
dev-stack:
	@test -f .env || (echo "Missing .env — copy from .env.example and edit. JWT_SECRET + INTERNAL_API_KEY required."; exit 1)
	docker compose up --build

dev-stack-down:
	docker compose down

dev-stack-logs:
	docker compose logs -f --tail=50

# ─── Test targets ──────────────────────────────────────────────────────────

# Run every component's tests. Fail-fast (Make default). For per-component
# isolation use the individual targets, or rely on the GH Actions matrix
# which runs them as parallel jobs.
test: test-backend test-poller test-proxy test-web test-mobile test-app test-cli

# Go backend: static analysis + compile + unit tests. Currently no test files
# exist; the command is wired so future tests run automatically.
test-backend:
	cd backend && go vet ./... && go build ./... && go test ./...

# ai-poller (Python, venv + requirements.txt). Creates the venv on demand,
# installs/syncs deps, then discovers and runs all test_*.py files.
test-poller:
	cd ai-poller && \
		( [ -d .venv ] || python3 -m venv .venv ) && \
		. .venv/bin/activate && \
		pip install --quiet --disable-pip-version-check -r requirements.txt && \
		python -m unittest discover -p 'test_*.py' -v

# claude-proxy (Python, uv-managed). `uv sync` resolves the lockfile, then
# `uv run` invokes the discover under the project's virtualenv.
test-proxy:
	cd claude-proxy && uv sync --quiet && uv run python -m unittest discover -p 'test_*.py' -v

# web (Vite + React). No jest setup yet — lint + production build catches
# type errors (tsc -b) and surface-level regressions. Add `vitest` later.
test-web:
	cd web && npm ci --silent && npm run lint && npm run build

# mobile (Expo + React Native). jest setup was removed alongside the deleted
# backup feature; type-checking is the meaningful gate for now.
test-mobile:
	cd mobile && npm ci --silent && npm run typescript

# Android app: unit tests only. The release APK build lives in
# .github/workflows/build.yml — don't duplicate that here.
test-app:
	./gradlew test --no-daemon

# CLI (Python). Installs the package, smoke-tests the entry point, and runs
# the unittest suite (click CliRunner with a mocked API client).
test-cli:
	cd cli && \
		( [ -d .venv ] || python3 -m venv .venv ) && \
		. .venv/bin/activate && \
		pip install --quiet --disable-pip-version-check -e . && \
		wp --help > /dev/null && \
		python -m unittest discover -s tests -p 'test_*.py' -v

# Install the CLI globally via pipx. Re-run to upgrade.
install-cli:
	@command -v pipx >/dev/null 2>&1 || (echo "pipx not found. brew install pipx"; exit 1)
	pipx install --force ./cli
	@echo "Installed. Try: wp --help"

# ─── Integration tests (isolated e2e stack) ────────────────────────────────
# A separate Postgres + backend on test ports (5433 / 8081), ephemeral DB.
# Defined in docker-compose.test.yml (project: workplanner-test) so it never
# clashes with the dev stack. Integration tests are Go, black-box HTTP, tagged
# `integration` so they're excluded from `make test-backend`.

# Bring the test stack up and wait for healthchecks (leave it running so you
# can poke at http://localhost:8081 yourself).
test-e2e-up:
	docker compose -f docker-compose.test.yml up --build -d --wait

# Tear the test stack down (removes its containers + ephemeral data).
test-e2e-down:
	docker compose -f docker-compose.test.yml down -v

# Run the integration suite against an already-running test stack.
test-integration:
	cd backend && \
		TEST_BASE_URL=$${TEST_BASE_URL:-http://localhost:8081} \
		TEST_INTERNAL_KEY=$${TEST_INTERNAL_KEY:-test-internal-key} \
		go test -tags=integration -count=1 -v ./tests/integration/...

# One-shot: bring the stack up, run the suite, tear it down (always — even on
# test failure). This is what CI runs.
test-e2e:
	docker compose -f docker-compose.test.yml up --build -d --wait
	@cd backend && \
		TEST_BASE_URL=http://localhost:8081 TEST_INTERNAL_KEY=test-internal-key \
		go test -tags=integration -count=1 -v ./tests/integration/... ; \
		status=$$? ; \
		cd .. && docker compose -f docker-compose.test.yml down -v ; \
		exit $$status
