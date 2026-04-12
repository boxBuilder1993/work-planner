# WorkPlanner

A multi-platform task manager with AI capabilities powered by Claude Agent SDK and LiteLLM.

---

## Running Locally (Docker)

Everything runs on your machine — no Railway, no Cloudflare tunnel.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Claude Code CLI](https://claude.ai/code) installed and logged in (`claude auth login`)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:
```
JWT_SECRET=<any long random string>    # openssl rand -hex 32
INTERNAL_API_KEY=<any long random string>
```

### 2. Start the Claude proxy (on host, outside Docker)

```bash
cd claude-proxy && ./start.sh
```

This runs on `localhost:8400`. The AI poller calls it via `host.docker.internal:8400`.
Keep this terminal open — it needs browser auth (Okta/claude.ai) to stay active.

### 3. Start everything else

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Web app | http://localhost:3000 |
| Backend API | http://localhost:8080 |
| ChromaDB | http://localhost:8000 |

### 4. Sign in

Open http://localhost:3000 — enter your email and name. No Google account needed.

### Android app

Point the API base URL to your machine's local IP (e.g. `http://192.168.x.x:8080`).

### Stopping

```bash
docker compose down          # stop containers, keep data
docker compose down -v       # stop and wipe all data
```

---

## AI Configuration

WorkPlanner uses LiteLLM for flexible AI model selection. You can use:
- **Claude Haiku** (default, cloud-based via Anthropic API)
- **Local models** via Ollama (e.g., qwen2.5:14b)
- **Other LiteLLM supported providers** (GPT-4, Llama, etc.)

### Quick Start

**Using Claude (via Anthropic):**
```bash
make ai-claude
# Then set ANTHROPIC_API_KEY in ai-poller/.env from 1Password
```

**Using Ollama (local model):**
```bash
make ai-ollama
# Automatically starts Ollama and pulls qwen2.5:14b
```

See [AI Configuration (Detailed)](#ai-configuration-detailed) below for details.

---

## Local AI Development

This project supports multiple AI providers for flexibility:
- **Ollama (local)**: Free, no API key needed
- **Anthropic Claude (cloud)**: Production-grade

### Option 1: Use Ollama Locally

1. Install Ollama: https://ollama.ai
2. Run: `make ai-ollama`
   - This pulls `qwen2.5:14b` and sets up environment
3. Run: `make dev-backend`
   - Starts backend with Ollama

### Option 2: Use Claude Haiku (Anthropic)

1. Get API key from https://console.anthropic.com
2. Store in 1Password under "Finance Planner" > "Anthropic API Key"
3. Run: `make ai-claude`
   - This fetches the key from 1Password
4. Run: `make dev-backend`
   - Starts backend with Claude

### Switch Between Providers

Simply run `make ai-ollama` or `make ai-claude` to switch, then `make dev-backend`.

### Environment Variables

The following env vars control the AI behavior:

| Var | Ollama | Claude | Railway |
|-----|--------|--------|---------|
| `AI_MODEL` | `ollama/qwen2.5:14b` | `claude-haiku-4-5` | Set on Railway UI |
| `AI_API_BASE` | `http://localhost:11434` | (empty) | (empty) |
| `AI_API_KEY` | (empty) | Your API key | Set on Railway secrets |

### Testing AI Endpoints

After `make dev-backend`, test the endpoints:

```bash
# Check AI status
curl http://localhost:8000/api/ai/status

# Test chat (requires auth token)
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}], "conversation_id": "test"}'
```

---

## AI Configuration (Detailed)

### Environment Variables

The AI Poller service uses these environment variables (in `ai-poller/.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MODEL` | `claude-haiku-4-5` | Model identifier (e.g., `claude-haiku-4-5`, `ollama/qwen2.5:14b`) |
| `AI_API_BASE` | *(empty)* | API endpoint URL (required for Ollama: `http://localhost:11434`) |
| `AI_API_KEY` | *(empty)* | API key for cloud providers (omit for Ollama) |
| `ANTHROPIC_API_KEY` | *(required for Claude)* | Anthropic API key from [1Password](https://1password.com) |

### Setting Up Claude Haiku

1. Get API key from 1Password (search: "Anthropic API Key")
2. Run: `make ai-claude`
3. Edit `ai-poller/.env`:
   ```env
   AI_MODEL=claude-haiku-4-5
   ANTHROPIC_API_KEY=sk-ant-...
   ```
4. Start the poller:
   ```bash
   cd ai-poller
   source .venv/bin/activate
   python main.py
   ```

### Setting Up Ollama (Local Model)

1. Install Ollama: https://ollama.ai
2. Run: `make ai-ollama`
   - Automatically starts Ollama daemon
   - Pulls qwen2.5:14b model
3. Edit `ai-poller/.env`:
   ```env
   AI_MODEL=ollama/qwen2.5:14b
   AI_API_BASE=http://localhost:11434
   AI_API_KEY=
   ```
4. Start the poller (same as Claude above)

### Railway Production Configuration

In Railway dashboard environment variables, set:

```
AI_MODEL=claude-haiku-4-5
AI_API_KEY=<your-anthropic-key>
ANTHROPIC_API_KEY=<same-key>
```

To change models in production without redeploying:
1. Update `AI_MODEL` in Railway dashboard
2. AI Poller picks up changes on next poll cycle (no restart needed)

Supported models on Railway:
- Any LiteLLM provider with valid API credentials
- Examples: `gpt-4`, `claude-3-opus`, `ollama/llama2` (with self-hosted Ollama)

---

# Temperature Converter

A lightweight Python library for converting temperatures between **Celsius (C)**, **Fahrenheit (F)**, and **Kelvin (K)**. A single `convert()` function covers all six direction combinations, enforces absolute-zero limits, and handles case-insensitive unit strings.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Celsius to Fahrenheit](#celsius-to-fahrenheit)
  - [Celsius to Kelvin](#celsius-to-kelvin)
  - [Fahrenheit to Celsius](#fahrenheit-to-celsius)
  - [Fahrenheit to Kelvin](#fahrenheit-to-kelvin)
  - [Kelvin to Celsius](#kelvin-to-celsius)
  - [Kelvin to Fahrenheit](#kelvin-to-fahrenheit)
- [Error Handling](#error-handling)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [License](#license)
- [Author](#author)

---

## Features

- Convert between all three temperature scales in one call
- Accepts unit strings case-insensitively (`"c"`, `"C"`, `"celsius"` → all work as `"C"`)
- Raises `ValueError` for unknown units or temperatures below absolute zero
- Raises `TypeError` for non-numeric input
- Zero external dependencies — pure Python 3

---

## Installation

### Option 1 — Clone the repository (recommended for development)

```bash
git clone https://github.com/<your-username>/temperature-converter.git
cd temperature-converter
```

### Option 2 — Clone into a virtual environment

```bash
git clone https://github.com/<your-username>/temperature-converter.git
cd temperature-converter

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# Install development dependencies (pytest)
pip install pytest
```

### Option 3 — Install via pip (if published to PyPI)

```bash
pip install temperature-converter
```

**Prerequisites:** Python 3.7 or later.

---

## Usage

Import the `convert` function and call it with a numeric value plus the source and target unit strings:

```python
from temperature_converter import convert

result = convert(value, from_unit, to_unit)
```

| Parameter   | Type    | Description                              |
|-------------|---------|------------------------------------------|
| `value`     | `float` | The temperature to convert               |
| `from_unit` | `str`   | Source unit: `"C"`, `"F"`, or `"K"`     |
| `to_unit`   | `str`   | Target unit: `"C"`, `"F"`, or `"K"`     |

Unit strings are **case-insensitive** and surrounding whitespace is ignored.

---

### Celsius to Fahrenheit

Formula: **°F = (°C × 9/5) + 32**

```python
from temperature_converter import convert

# Water freezing point
print(convert(0, "C", "F"))      # 32.0

# Water boiling point
print(convert(100, "C", "F"))    # 212.0

# Human body temperature
print(convert(37, "C", "F"))     # 98.6

# Crossover point (C and F are equal)
print(convert(-40, "C", "F"))    # -40.0

# Absolute zero
print(convert(-273.15, "C", "F"))  # -459.67
```

---

### Celsius to Kelvin

Formula: **K = °C + 273.15**

```python
from temperature_converter import convert

# Water freezing point
print(convert(0, "C", "K"))      # 273.15

# Water boiling point
print(convert(100, "C", "K"))    # 373.15

# Room temperature
print(convert(25, "C", "K"))     # 298.15

# Absolute zero
print(convert(-273.15, "C", "K"))  # 0.0
```

---

### Fahrenheit to Celsius

Formula: **°C = (°F − 32) × 5/9**

```python
from temperature_converter import convert

# Water freezing point
print(convert(32, "F", "C"))     # 0.0

# Water boiling point
print(convert(212, "F", "C"))    # 100.0

# Human body temperature
print(convert(98.6, "F", "C"))   # 37.0

# Crossover point
print(convert(-40, "F", "C"))    # -40.0

# Absolute zero
print(convert(-459.67, "F", "C"))  # -273.15
```

---

### Fahrenheit to Kelvin

Formula: **K = (°F − 32) × 5/9 + 273.15**

```python
from temperature_converter import convert

# Water freezing point
print(convert(32, "F", "K"))     # 273.15

# Water boiling point
print(convert(212, "F", "K"))    # 373.15

# Absolute zero
print(convert(-459.67, "F", "K"))  # 0.0

# Room temperature (72 °F)
print(convert(72, "F", "K"))     # 295.3722222222
```

---

### Kelvin to Celsius

Formula: **°C = K − 273.15**

```python
from temperature_converter import convert

# Absolute zero
print(convert(0, "K", "C"))      # -273.15

# Water freezing point
print(convert(273.15, "K", "C"))  # 0.0

# Water boiling point
print(convert(373.15, "K", "C"))  # 100.0

# Sun's surface (~5778 K)
print(convert(5778, "K", "C"))   # 5504.85
```

---

### Kelvin to Fahrenheit

Formula: **°F = (K − 273.15) × 9/5 + 32**

```python
from temperature_converter import convert

# Absolute zero
print(convert(0, "K", "F"))      # -459.67

# Water freezing point
print(convert(273.15, "K", "F"))  # 32.0

# Water boiling point
print(convert(373.15, "K", "F"))  # 212.0

# Room temperature (298.15 K)
print(convert(298.15, "K", "F"))  # 68.0
```

---

## Error Handling

```python
from temperature_converter import convert

# Unknown unit → ValueError
convert(100, "X", "C")
# ValueError: Unknown unit 'X'. Valid units: ['C', 'F', 'K']

# Below absolute zero → ValueError
convert(-300, "C", "F")
# ValueError: -300 C is below absolute zero (-273.15 C)

# Non-numeric value → TypeError
convert("hot", "C", "F")
# TypeError: value must be a number, got 'str'

# Case-insensitive units work fine
print(convert(0, "c", "f"))   # 32.0  ✓
print(convert(0, " C ", " F "))  # 32.0  ✓
```

---

## Running Tests

The test suite is written with the standard `unittest` module and is compatible with **pytest**.

### Run all tests with pytest (recommended)

```bash
pytest test_temperature_converter.py
```

### Run all tests with verbose output

```bash
pytest test_temperature_converter.py -v
```

### Run a specific test class

```bash
pytest test_temperature_converter.py::TestCelsiusToFahrenheit -v
```

### Run a specific test method

```bash
pytest test_temperature_converter.py::TestCelsiusToFahrenheit::test_boiling -v
```

### Run with the built-in unittest runner

```bash
python -m unittest test_temperature_converter
```

### Expected output (pytest -v)

```
test_temperature_converter.py::TestCelsiusToFahrenheit::test_absolute_zero PASSED
test_temperature_converter.py::TestCelsiusToFahrenheit::test_body_temperature PASSED
test_temperature_converter.py::TestCelsiusToFahrenheit::test_boiling PASSED
test_temperature_converter.py::TestCelsiusToFahrenheit::test_freezing PASSED
test_temperature_converter.py::TestCelsiusToFahrenheit::test_negative PASSED
...
================================ 35 passed in 0.12s ================================
```

---

## Project Structure

```
temperature-converter/
├── temperature_converter.py     # Main library — convert() function
├── test_temperature_converter.py  # Full test suite (unittest / pytest)
└── README.md                    # This file
```

---

## License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2026 Temperature Converter Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Author

Maintained by the project contributors.

- **GitHub:** [https://github.com/&lt;your-username&gt;/temperature-converter](https://github.com/<your-username>/temperature-converter)
- **Issues:** [https://github.com/&lt;your-username&gt;/temperature-converter/issues](https://github.com/<your-username>/temperature-converter/issues)

Contributions, bug reports, and feature requests are welcome!
