PY := .venv/bin/python
OLLAMA ?= $(shell command -v ollama || echo $(HOME)/Applications/Ollama.app/Contents/Resources/ollama)
export TOKENIZERS_PARALLELISM=false

.PHONY: video share setup data pipeline forecast plan scenarios replay eval eval-llm models web dev api test demo-cache reset mcp all

setup:            ## Python venv + web deps
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd web && npm install

data:             ## download Boston 311 CSVs (2022-2025) from data.boston.gov
	$(PY) -m data.download

pipeline:         ## clean + build monthly/daily/catalog tables, and the City Pulse map layers
	$(PY) -m data.pipeline && $(PY) -m data.pulse

forecast:
	$(PY) -m forecast.model

plan:             ## calibrate crews, solve plans, baselines, frontier
	$(PY) -m optimizer.run

scenarios:        ## sensitivity, storm, 100-year simulation, robust plan, tornado
	$(PY) -m scenarios.scenario

replay:           ## real 2025 demand replayed month by month (plan + monitor vs flat vs hindsight)
	$(PY) -m scenarios.replay

eval:             ## intake evaluation without the LLM (about 1 minute)
	$(PY) -m eval.build_testset && $(PY) -m eval.run_eval --mode retrieval

eval-llm:         ## intake evaluation with the local LLM (about 1 hour on CPU; resumes)
	$(PY) -m eval.run_eval --mode llm

models:           ## pull the local models into Ollama
	$(OLLAMA) pull qwen2.5:3b && $(OLLAMA) pull moondream

all: pipeline forecast plan scenarios replay eval

web:
	cd web && npm run build

api:
	$(PY) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

dev:              ## one command: API on :8000 (serves the built UI) + Vite dev server on :5173
	cd web && npm run build
	( $(PY) -m uvicorn api.main:app --host 0.0.0.0 --port 8000 & cd web && npm run dev -- --port 5173 ; kill %1 )

demo-cache:       ## pre-run every demo input through the local LLM so the live demo never waits
	$(PY) -m scripts.warm_demo_cache

video:            ## record the product demo video by driving the real app (run `make api` first) -> video/out/
	$(MAKE) reset
	cd video && npm install --silent && node make_video.mjs
	$(MAKE) reset

share:            ## public HTTPS link via a free Cloudflare tunnel (run `make api` first); QR code follows it
	$(PY) -m scripts.share

reset:            ## clear the app database (intake log, traces, proposals) before a demo
	rm -f data/app.sqlite && cp contracts/plan_history/plan_original.json contracts/plan.json 2>/dev/null || true

test:
	$(PY) -m pytest tests -q

mcp:              ## run the tool registry as an MCP server (stdio), e.g. for Claude Desktop
	$(PY) -m agents.mcp_server
