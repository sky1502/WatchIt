# WatchIt

Local-first parental monitoring with a multi-stage safety pipeline and an on-device LLM
judge (via Ollama). No cloud calls, no telemetry—everything runs on your machine.

## Table of Contents
- [Why WatchIt](#why-watchit)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick Start (macOS)](#quick-start-macos)
- [Manual Setup](#manual-setup)
- [Running the Services](#running-the-services)
  - [FastAPI backend](#fastapi-backend)
  - [Next.js dashboard](#nextjs-dashboard)
  - [Streamlit dashboard](#streamlit-dashboard)
  - [Chrome/Chromium extension](#chromechromium-extension)
- [Configuration](#configuration)
- [API Surface](#api-surface)
- [Data & Security](#data--security)
- [Development Notes](#development-notes)

## Why WatchIt
- **Private by design** – Event capture, analysis, and policy enforcement stay on-device.
- **Layered safety checks** – Fast keyword heuristics, optional OCR/ASR, and an agentic LLM
  (LangGraph + Ollama) collaborate on every event.
- **Live enforcement** – A Chromium extension streams policy decisions via server-sent events
  (SSE) and can warn, blur, or block pages in real time.
- **Configurable policies** – Built-in quiet hours, allow/block lists, and LLM overridable
  categories; every setting is overrideable via environment variables.
- **Auditable history** – SQLCipher-backed datastore captures events, analysis artifacts, and
  the final policy decision for review.

## How It Works
1. The browser extension emits a `visit` event when navigation commits, including a DOM text
   sample and metadata.
2. The FastAPI backend (`app/main.py`) stores the event, runs the LangGraph workflow, and
   persists both heuristic scores and LLM judgements.
3. The policy engine (`policy/engine.py`) folds in schedules, allow/block lists, and model
   outputs to produce an action (`allow`, `warn`, `blur`, `block`, `notify`).
4. Final decisions are published over SSE so the extension and dashboards react instantly.
5. Dashboards (`ui` Next.js app or `dashboard.py` Streamlit app) display live and historical
   events for guardians.

## Prerequisites
- macOS 13+ is the primary target (Linux/Windows work with equivalent tooling).
- Python 3.11 (minimum 3.10).
- Node.js 18+ (for the Next.js dashboard).
- [Ollama](https://ollama.com/) installed and running locally.
- (Optional) Tesseract OCR and Whisper runtime for screenshot/audio analysis. The `Brewfile`
  includes everything needed on macOS.

## Quick Start (macOS)
```bash
# 1) Clone and enter the repo
git clone <your-fork-url> && cd WatchIt

# 2) Run the bootstrap script (installs Brew deps, Python venv, pulls Ollama model)
./setup.sh

# 3) Launch the API
source .venv/bin/activate
uvicorn app.main:app --reload
```

When `setup.sh` completes you will have:
- A Python virtualenv in `.venv`.
- All Python requirements installed.
- Ollama running locally with the `llama3.1` model pulled (adjust in `.env` if desired).

## Manual Setup
Prefer to wire things up by hand? Follow these steps:

```bash
# Install Python dependencies
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# Start Ollama and pull a model used by the judge
ollama serve &
ollama pull qwen2.5:7b-instruct-q4_K_M  # or llama3.1, change via WATCHIT_OLLAMA_MODEL
```

Enable OCR/ASR support by installing the optional Brew packages (Tesseract, FFmpeg) or
disable them by setting `WATCHIT_ENABLE_OCR=false` / `WATCHIT_ENABLE_ASR=false`.

## Running the Services

### FastAPI backend
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 4849
```
The interactive OpenAPI docs are available at `http://127.0.0.1:4849/docs`.

### Next.js dashboard
```bash
cd ui
npm install
npm run dev   # serves on http://127.0.0.1:4848 by default
```
The dashboard consumes the REST/SSE endpoints from the backend and shows live decisions as
they land.

### Streamlit dashboard
For a quick standalone dashboard, run:
```bash
source .venv/bin/activate
streamlit run dashboard.py
```
Use the sidebar controls to filter by child ID and adjust history depth.

### Chrome/Chromium extension
1. Navigate to `chrome://extensions`, enable **Developer mode**, and choose **Load unpacked**.
2. Point Chrome at the `extension_chromium` directory.
3. The service worker (`background.js`) will subscribe to `{API}/v1/stream/decisions` and
   enforce actions on every tab.
4. The content script (`content.js`) renders warnings, blurs media, or shows a blocking
   interstitial based on policy action.

## Configuration
Override defaults via a `.env` file. The most relevant settings (see `core/config.py` for
the complete list):

| Variable | Purpose | Default |
| --- | --- | --- |
| `WATCHIT_DB_PATH` | SQLCipher database path | `child_monitor.db` |
| `WATCHIT_DB_KEY` | Encryption key (change this!) | `change_this_strong_key` |
| `WATCHIT_PARENT_PIN` | PIN required to pause/resume monitoring | `123456` |
| `WATCHIT_SCHEDULE_DAYS` | CSV of quiet-hour days | `Mon,Tue,Wed,Thu` |
| `WATCHIT_SCHEDULE_QUIET` | Quiet-hour window (`HH:MM-HH:MM`) | `21:00-07:00` |
| `WATCHIT_OLLAMA_MODEL` | LLM used by the judge | `qwen2.5:7b-instruct-q4_K_M` |
| `WATCHIT_ENABLE_OCR` / `WATCHIT_ENABLE_ASR` | Enable screenshot/audio parsing | `true` |

Update the `.env` file before starting the backend so the settings are loaded at launch.

## API Surface
- `POST /v1/event` – ingest a single event. Body must match `app.api_models.EventInput`.
- `GET /v1/events` – fetch recent events (filter by `child_id`, limit default 50).
- `GET /v1/decisions` – fetch recent decisions.
- `GET /v1/stream/decisions` – SSE stream of new decisions as they are made.
- `POST /v1/control/pause` – pause enforcement for `minutes` (requires parent PIN).
- `POST /v1/control/resume` – resume monitoring (requires parent PIN).

Sample event payload:
```json
{
  "child_id": "child_main",
  "ts": 1717000000000,
  "kind": "visit",
  "url": "https://example.com",
  "title": "Example Domain",
  "tab_id": "tab-123",
  "data_json": "{\"dom_sample\": \"Example content...\"}"
}
```

## Data & Security
- **Database** – Stored in SQLCipher (`core/db.py`) with hardened pragmas. Change
  `WATCHIT_DB_KEY` for each deployment.
- **Privacy model** – No external API calls besides Ollama’s local HTTP server; the LLM stays
  on-device.
- **Policy engine** – `policy/engine.py` enforces quiet hours, allow/block lists, and merges
  heuristic/LLM scores. Customize to match family policy needs.

## Development Notes
- `make setup` mirrors the quick start steps using the included `Makefile`.
- `make run` boots the API through `uvicorn`.
- `make clean` clears the virtualenv and `__pycache__`.
- The LangGraph workflow lives in `analysis/graph.py`; tweak existing nodes or add your own
  to extend the pipeline.
- Keep an eye on `ollama serve` logs in `/tmp/ollama.log` (written by `setup.sh`) when
  debugging model issues.

## Roadmap & Vision
- **Working prototype** – The initial milestone is a production-quality local prototype that
  ties the capture pipeline, policy analysis, and enforcement surfaces together end to end.
- **Prompt experimentation** – Multiple handcrafted prompts (varying tone, constraints, and
  context length) are evaluated against the same events to benchmark precision, recall, and
  latency before locking in defaults.
- **Curated decision store** – Blocked and allowed URLs persist in the local datastore so
  supervisors can audit outcomes, override mistakes, and promote/demote entries with a single
  click.
- **Supervisor pause control** – A PIN-gated pause timer lets adults temporarily relax
  monitoring (e.g., 15-minute blocks) and resume with a single action.
- **Unified supervisor console** – A richer UI will surface all monitored devices, exposing
  per-device strictness profiles, schedule overrides, and real-time status indicators for
  quick adjustments.
