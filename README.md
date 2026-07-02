# IBM BOB HTTP Server

> **Expose IBM BOB Shell as an OpenAI/Ollama-compatible HTTP API server**  
> Use IBM BOB with LM Studio, Open WebUI, Continue.dev, Cursor, or any OpenAI-compatible client.

---

## What This Does

This server wraps the `bob` CLI and exposes it through **standard HTTP APIs** that work exactly like:
- **Ollama** (`/api/tags`, `/api/generate`, `/api/chat`, `/api/show`)
- **OpenAI** (`/v1/models`, `/v1/chat/completions`, `/v1/completions`)
- **LM Studio** (uses OpenAI format)

You can now point **any** AI client at `http://localhost:31013` and use IBM BOB Shell as a model.

---

## Quick Start

```bash
# 1. Navigate to server directory
cd ~/ibm-bob-http-server

# 2. Start the server in the background
./run-ollama-proxy.sh

# 3. Test it works
curl http://localhost:31013/v1/models
```

**Expected output:**
```json
{
  "object": "list",
  "data": [
    {"id": "ibm-bob-ollama", "object": "model", "name": "IBM BOB (Ollama Mode)", ...},
    {"id": "ibm-bob-chat", "object": "model", "name": "IBM BOB Chat", ...},
    {"id": "ibm-bob-code", "object": "model", "name": "IBM BOB Code", ...}
  ]
}
```

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **IBM BOB Shell** | Must be installed and `bob` in PATH. Download from [bob.ibm.com](https://bob.ibm.com) |
| **Python 3.11+** | For the HTTP server |
| **Authenticated BOB session** | Run `bob` once manually to authenticate before using the API |

### Authenticate BOB (Required!)

```bash
# Run once to authenticate
bob

# You'll see:
# - License agreement (accept)
# - IBMid login (sign in)
# - Success message
```

---

## Available Models

| Model ID | Mode | Best For |
|----------|------|----------|
| `ibm-bob-ollama` | code | General chat + code generation |
| `ibm-bob-chat` | ask | Natural language conversation |
| `ibm-bob-code` | code | Code generation/analysis (8K tokens) |

---

## API Endpoints

### OpenAI-Compatible (port 31013)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/models` | List available models |
| `POST` | `/v1/chat/completions` | Chat completions |
| `POST` | `/v1/completions` | Text completions |
| `GET` | `/health` | Health check |

### Ollama-Compatible (port 31013)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tags` | List models (Ollama format) |
| `GET` | `/api/show/{model}` | Show model info |
| `POST` | `/api/generate` | Generate completion |

---

## Usage Examples

### 1. OpenAI Client (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:31013/v1",
    api_key="not-needed"  # Any string works
)

response = client.chat.completions.create(
    model="ibm-bob-code",
    messages=[{"role": "user", "content": "Write a Python function to calculate fibonacci"}]
)
print(response.choices[0].message.content)
```

### 2. LM Studio

1. Open LM Studio
2. Go to **Settings** → **Developer** → **Local Server**
3. Set **Base URL** to: `http://localhost:31013/v1`
4. Select any model from the list (ibm-bob-ollama, ibm-bob-chat, ibm-bob-code)
5. Start chatting!

### 3. Open WebUI

```bash
docker run -d -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:31013/v1 \
  -e OPENAI_API_KEY=not-needed \
  ghcr.io/open-webui/open-webui:main
```

Then visit `http://localhost:3000` and configure the model.

### 4. Continue.dev (VS Code)

```json
// .continue/config.json
{
  "models": [
    {
      "title": "IBM BOB Code",
      "provider": "openai",
      "model": "ibm-bob-code",
      "apiBase": "http://localhost:31013/v1",
      "apiKey": "not-needed"
    }
  ]
}
```

### 5. curl (Direct API)

```bash
# List models
curl http://localhost:31013/v1/models

# Chat completion
curl -X POST http://localhost:31013/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ibm-bob-code",
    "messages": [{"role": "user", "content": "Explain this code"}]
  }'

# Ollama format
curl http://localhost:31013/api/tags
```

---

## Server Management

| Command | Description |
|---------|-------------|
| `./run-ollama-proxy.sh` | Start server in background (auto-venv, deps) |
| `./stop-ollama-proxy.sh` | Stop server and show recent logs |
| `tail -f logs/server.log` | View live server logs |

### Manual Start (Debug)

```bash
cd /Users/himanshusao/Work/src/extra/pi-agent/ibm-bob-http-server
source .venv/bin/activate
python3 server.py
```

---

## Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────┐     CLI      ┌────────────┐
│  Any AI Client  │ ─────────────▶│  HTTP Server     │ ────────────▶│  bob CLI   │
│  (LM Studio,    │   (OpenAI/    │  (FastAPI,       │   subprocess │  (IBM BOB  │
│   Continue,     │    Ollama)    │   Uvicorn)       │              │   Shell)   │
│   Open WebUI)   │ ◀─────────────│  Port: 31013     │ ◀────────────│            │
└─────────────────┘     JSON      └──────────────────┘   stdout     └────────────┘
```

---

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BOB_PATH` | `bob` | Path to BOB executable |
| `PORT` | `31013` | Server port |

```bash
# Custom port
PORT=8080 ./run-ollama-proxy.sh

# Custom BOB path
BOB_PATH=/usr/local/bin/bob ./run-ollama-proxy.sh
```

---

## Troubleshooting

### "Authentication timeout" / Empty responses
```bash
# Run BOB manually to authenticate
bob
# Accept license, sign in with IBMid
```

### Port already in use
```bash
./stop-ollama-proxy.sh
# Or manually:
lsof -t -i :31013 | xargs kill -9
```

### Python dependencies failing
```bash
cd ibm-bob-http-server
rm -rf .venv
./run-ollama-proxy.sh  # Recreates venv and installs deps
```

### BOB not found
```bash
which bob
# If not found, install from https://bob.ibm.com
# Or add to PATH: export PATH=$PATH:/path/to/bob
```

---

## File Structure

```
ibm-bob-http-server/
├── server.py              # Main FastAPI server
├── run-ollama-proxy.sh    # Start script (background, auto-venv)
├── stop-ollama-proxy.sh   # Stop script (kills by port)
├── requirements-ollama.txt # Python dependencies
├── logs/
│   └── server.log         # Server execution logs
└── README.md              # This file
```

---

## Dependencies

```txt
fastapi==0.110.2
uvicorn==0.29.0
python-multipart==0.0.6
pydantic==2.7.1
```

---

## License

MIT License - Use freely for personal or commercial projects.

---

## Support

- **IBM BOB Docs**: https://bob.ibm.com/docs/shell
- **Issues**: Create GitHub issue in this repo
- **BOB CLI Help**: `bob --help`

---

**Built for developers who want to use IBM BOB Shell anywhere OpenAI/Ollama APIs work.** 🚀
