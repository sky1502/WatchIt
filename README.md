# WatchIt

Local-first parental monitoring with a multi-stage safety pipeline and an on-device LLM
judge (via Ollama). No cloud calls, no telemetry—everything runs on your machine.

## Table of Contents
- [Why WatchIt](#why-watchit)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick Start (macOS)](#quick-start-macos)
- [Quick Start (Windows)](#quick-start-windows)
- [Manual Setup](#manual-setup)
- [Environment Files](#environment-files)
- [Running the Services](#running-the-services)
  - [FastAPI backend](#fastapi-backend)
  - [Next.js dashboard](#nextjs-dashboard)
  - [Chrome/Chromium extension](#chromechromium-extension)
  - [Postgres replicator (optional)](#postgres-replicator-optional)
- [Configuration](#configuration)
- [API Surface](#api-surface)
- [Data & Security](#data--security)
- [Development Notes](#development-notes)

## Why WatchIt
- **Private by design** – Event capture, analysis, and policy enforcement stay on-device.
- **Layered safety checks** – Fast keyword heuristics, optional PaddleOCR screenshot parsing, and an agentic LLM
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
2. The FastAPI backend (`app/main.py`) stores the event, then runs an **agent pipeline**:
   - **URL/Metadata Agent** inspects DOM/text, calls the on-device LLM, and emits a decision
     with confidence tied to the child’s strictness/age.
   - **Headlines Agent** focuses on titles/headlines to raise or lower risk.
   - **Screenshot + OCR Agents** collaborate when the confidence is low; the backend tells the
     extension to capture screenshots, and PaddleOCR extracts extra text for a second pass.
3. The policy engine (`policy/engine.py`) folds in schedules, allow/block lists, agent output,
   and model confidence to produce an action (`allow`, `warn`, `blur`, `block`, `notify`).
4. Final decisions are published over SSE so the extension and dashboards react instantly.
5. The Next.js dashboard (`ui` folder) displays live and historical events for guardians
   after they sign in with a Google account provisioned in Firebase. It reads from the
   Postgres mirror and lets guardians edit per-child strictness + age to steer the LLM. The
   LLM also returns a confidence score; only when confidence is low do the screenshot/OCR
   agents run.

## Agent Architecture
| Agent | Purpose | Key Tools |
| --- | --- | --- |
| **Headlines Agent (Layer 1)** | Fast heuristics over URL/title + keyword scores. If confidence is high it can allow/block instantly without waking heavier agents. | SafetyAnalyzer, domain/title keyword lists |
| **URL/Metadata Agent (Layer 2)** | When the first layer is unsure, this agent ingests DOM text/metadata and queries the on-device LLM for a structured verdict tuned to child strictness/age. | SafetyAnalyzer (reused), `ChatOllama` |
| **Screenshots Agent** | Decides if screenshots are available and whether the browser must capture new ones when the LLM confidence stays low. | Browser extension hooks, event payload metadata |
| **OCR Agent (Layer 3)** | Runs PaddleOCR on screenshots and feeds the extracted text back through the URL/Metadata agent for a final pass. | `analysis/ocr_asr.py`, PaddleOCR |

Each agent writes its findings into the `MonitorState`, and the policy engine consumes the combined view before publishing the final action.

**Layered flow**
1. **Headlines layer** runs immediately—if it’s confident enough, the system blocks/allows without hitting the LLM.
2. Only when the first layer warns or stays low-confidence does the **URL/Metadata layer** run the LLM. Its confidence determines whether OCR is required.
3. When the LLM still isn’t sure, the SSE response instructs the extension to capture screenshots so the **Screenshots + OCR layer** can enrich the text and rerun the LLM, after which the policy engine makes the final call.

## Prerequisites
- Python 3.11 (minimum 3.10).
- Node.js 18+ (for the Next.js dashboard).
- [Ollama](https://ollama.com/) installed and running locally.
- (Optional) PaddleOCR runtime (PaddlePaddle + PaddleOCR Python packages) if you plan to use
  screenshot text extraction.

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

## Quick Start (Windows)
```powershell
# 1) Clone and enter the repo
git clone <your-fork-url>
cd WatchIt

# 2) Create + activate a virtual environment (PowerShell)
py -3.11 -m venv .venv
.\.venv\Scripts\activate

# 3) Install Python dependencies
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# 4) Install Node.js 18+ (https://nodejs.org/) and Ollama for Windows (https://ollama.com/download)
#    Run `ollama serve` once, then pull your preferred model:
ollama pull qwen2.5:7b-instruct-q4_K_M

# 5) Create `.env` (repo root)—copy from `.env.example` if you keep one—fill in secrets, then start the API
uvicorn app.main:app --reload --host 127.0.0.1 --port 4849
```
Windows does not ship with Homebrew, so use `winget`/`choco` for system dependencies (Git, Python,
Node.js, SQLite/SQLCipher) as needed. Dashboard/extension commands are identical once the backend is
running.

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

Enable OCR support by keeping the default Python dependencies (PaddleOCR + PaddlePaddle). To
skip screenshot parsing entirely, set `WATCHIT_ENABLE_OCR=false` in `.env`.

## Environment Files
- **Backend `.env` (repo root)** – create this file
  and populate the environment variables consumed by `core/config.py`. A minimal file looks like:

  ```dotenv
  WATCHIT_DB_PATH=
  WATCHIT_DB_KEY=change_this_strong_key
  WATCHIT_PARENT_PIN=
  WATCHIT_BIND_HOST=
  WATCHIT_BIND_PORT=
  WATCHIT_OLLAMA_MODEL=
  WATCHIT_ENABLE_OCR=
  WATCHIT_PG_DSN=  # optional, needed for Postgres mirroring
  ```

  Store secrets (DB key, PIN, Postgres credentials) in this file. The FastAPI app
  automatically reads it via `python-dotenv`.

- **Dashboard `ui/.env.local`** – lives inside the `ui` folder and powers Next.js + Firebase auth:

  ```dotenv
  NEXT_PUBLIC_FIREBASE_API_KEY=AIza...
  NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=project.firebaseapp.com
  NEXT_PUBLIC_FIREBASE_PROJECT_ID=project-id
  NEXT_PUBLIC_FIREBASE_APP_ID=1:123:web:abc
  WATCHIT_DASHBOARD_API_BASE=http://127.0.0.1:4849  # optional helper for fetch calls
  ```

- Keep `.env` and `ui/.env.local` synchronized with the same API host/port you expose via
  `WATCHIT_BIND_HOST`/`WATCHIT_BIND_PORT` so the dashboard and extension can talk to the backend.

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
cp .env.local.example .env.local  # fill with Firebase config
npm run dev   # serves on http://127.0.0.1:4848 by default
```
Before starting the dashboard:
1. Create a Firebase project (https://console.firebase.google.com/), enable **Authentication → Sign-in method → Google**.
2. Copy the Web app credentials into `ui/.env.local`:
   - `NEXT_PUBLIC_FIREBASE_API_KEY`
   - `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
   - `NEXT_PUBLIC_FIREBASE_PROJECT_ID`
   - `NEXT_PUBLIC_FIREBASE_APP_ID`
3. Configure Postgres access for the backend/replicator via `WATCHIT_PG_DSN` and keep the
   replicator running so the dashboard can read mirrored data.
4. Load `http://127.0.0.1:4848` and sign in with an approved Google (Gmail) account.

Once authenticated the dashboard:
- Reads historical events/decisions straight from Postgres.
- Streams in fresh decisions via SSE for real-time awareness.
- Exposes PIN-based pause/resume plus per-child controls for **strictness** (lenient,
  standard, strict) and **child age** that immediately influence the LLM prompt/policy.

### Chrome/Chromium extension
1. Ensure the FastAPI backend is running and reachable (match the host/port in the steps below).
2. Open `extension_chromium/background.js` and update `const API = "http://127.0.0.1:4849";` (and
   `childId` if you track multiple children) so it points to your backend.
3. In Chrome/Chromium visit `chrome://extensions`, enable **Developer mode**, and choose **Load
   unpacked**.
4. Select the `extension_chromium` directory. Chrome will load `manifest.json` plus the service
   worker.
5. The service worker subscribes to `${API}/v1/stream/decisions` via SSE and relays decisions to
   every tab. When the backend responds with `needs_ocr=true`, the extension captures a screenshot
   and posts it to `${API}/v1/event/upgrade`.
6. The content script (`content.js`) listens for those decisions and renders warnings, blur effects,
   or a blocking interstitial.

### Postgres replicator (optional)
Need a centralized datastore while keeping the low-latency local path? Use
`runtime/pg_replicator.py` to mirror SQLCipher rows into Postgres without slowing the main
pipeline.

```bash
WATCHIT_PG_DSN="postgresql://user:pass@localhost/watchit" \
python -m runtime.pg_replicator
```

By default the replicator:
- Polls SQLite every 5 seconds for new events/decisions and upserts child profiles.
- Creates `watchit_events` and `watchit_decisions` tables in Postgres (JSONB columns for the
  original payloads) plus `watchit_children` for child metadata (strictness, age).
- Tracks progress in the SQLite `settings` table (`pg_last_event_ts`, `pg_last_decision_ts`)
  so restarts resume where they left off.

Embed it into another service with:

```python
from runtime.pg_replicator import PostgresReplicator
replicator = PostgresReplicator(pg_dsn=os.environ["WATCHIT_PG_DSN"])
asyncio.create_task(replicator.run_forever())
```

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
| `WATCHIT_ENABLE_OCR` | Enable screenshot parsing via PaddleOCR | `true` |
| `WATCHIT_OCR_CONFIDENCE_THRESHOLD` | Confidence cut-off (0-1) before OCR upgrade required | `0.7` |
| `WATCHIT_PG_DSN` | Postgres connection string for mirrored data | _unset_ |

Dashboard env vars (`ui/.env.local`) control Firebase authentication for the web dashboard:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Web API key from the Firebase project |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Auth domain (e.g., `project.firebaseapp.com`) |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | App ID from Firebase console |

Update the `.env` file before starting the backend so the settings are loaded at launch.

## API Surface
- `POST /v1/event` – ingest a single event. Body must match `app.api_models.EventInput`.
- Responses from `/v1/event` and SSE payloads include `confidence` (LLM certainty 0-1) and
  `needs_ocr` (whether the browser should capture a screenshot for OCR).
- `GET /v1/events` – fetch recent events (filter by `child_id`, limit default 50).
- `GET /v1/decisions` – fetch recent decisions.
- `GET /v1/children` – list mirrored child profiles (strictness, age).
- `POST /v1/children/{child_id}/settings` – update a child's strictness/age (reflected in SQLite + Postgres).
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
