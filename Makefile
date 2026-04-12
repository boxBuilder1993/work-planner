.PHONY: ai-ollama ai-claude dev-backend help

help:
	@echo "Available AI targets:"
	@echo "  make ai-ollama      - Start Ollama and configure for qwen2.5:14b model"
	@echo "  make ai-claude      - Configure for Claude Haiku (requires 1Password CLI)"
	@echo "  make dev-backend    - Start backend with configured AI provider"

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
