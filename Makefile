.PHONY: setup venv deps run start-ollama pull-model db-init clean


VENV=.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip


setup: venv deps start-ollama pull-model ## Full local setup


venv:
python3.11 -m venv $(VENV)
@echo "Activate with: source $(VENV)/bin/activate"


deps:
$(PIP) install --upgrade pip wheel setuptools
$(PIP) install -r requirements.txt


start-ollama:
pgrep -x "ollama" >/dev/null 2>&1 || (ollama serve >/tmp/ollama.log 2>&1 & sleep 2)


pull-model:
ollama pull llama3.1


run:
$(VENV)/bin/uvicorn app.main:app --reload


db-init:
$(VENV)/bin/alembic upgrade head


clean:
rm -rf $(VENV)
find . -name "__pycache__" -type d -exec rm -rf {} +