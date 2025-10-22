# WatchIt (Local, macOS-first)

Local parental monitoring pipeline with agentic LLM judge via **Ollama** (no cloud calls).

## Prereqs
- Python 3.10+ (3.11 recommended)
- macOS preferred (works on Linux/Windows too)
- Ollama installed: https://ollama.com
- Model pulled locally (default): `qwen2.5:7b-instruct-q4_K_M`

```bash
# install ollama and run service
brew install ollama
ollama serve &
ollama pull qwen2.5:7b-instruct-q4_K_M
# or: ollama pull llama3.1:8b-instruct-q4_K_M
