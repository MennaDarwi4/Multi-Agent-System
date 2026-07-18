# 🧠 Multi-Agent AI System

A fully functional **multi-agent AI system** that retrieves data from
heterogeneous sources, processes and summarizes it with LLMs, and performs
automated actions — generating a report, drafting an email, and building a live
dashboard — all coordinated by an orchestrator with sequential *and* parallel
stages.

Deployable two ways: **Streamlit + ngrok** (visual UI, ideal for the demo video)
or **FastAPI** (REST API for automation).

---

## How it maps to the project objectives

| # | Objective | Where it lives |
|---|-----------|----------------|
| 1 | **Data Retrieval** (PDF, Sheets, APIs, DBs) | `agents/retrieval_agent.py` — PDF, CSV/TSV, public Google Sheets, JSON APIs, web pages, raw text |
| 2 | **Processing & Summarization** with LLMs | `agents/summarizer_agent.py` (per-source) + `agents/analysis_agent.py` (cross-source synthesis, structured JSON) |
| 3 | **Automated Actions** (emails, reports, dashboards) | `agents/report_agent.py` (Markdown + PDF), `agents/email_agent.py` (draft + optional SMTP send), `agents/dashboard_agent.py` (metrics + charts) |
| 4 | **Workflow Orchestration** (sequential + parallel) | `orchestrator.py` — sequential stages with a **parallel** summarization stage (thread pool) |
| 5 | **Presentation & Explanation** | `app.py` (Streamlit UI with a live run trace) + the *Demo script* below |
| 6 | **Testing & Evaluation** | `tests/test_pipeline.py` (pytest) + `evaluation/evaluate.py` (reliability / accuracy / efficiency report) |

---

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │              Orchestrator                 │
                    │   (shared LLMClient + shared RunTrace)     │
                    └──────────────────────────────────────────┘
                                     │
   Stage 1            Stage 2 (∥)            Stage 3           Stage 4 (actions)
 ┌───────────┐   ┌──────────────────┐   ┌───────────┐   ┌──────────────────────┐
 │ Retrieval │──▶│   Summarizer ×N   │──▶│ Analysis  │──▶│ Report │ Email │ Dash │
 │  Agent    │   │ (parallel threads)│   │  Agent    │   │  Agent │ Agent │ Agent│
 └───────────┘   └──────────────────┘   └───────────┘   └──────────────────────┘
   PDF/CSV/         LLM summary per        cross-source      Markdown+PDF │ draft │
   Sheet/API/       source (+ extractive   synthesis →       email │ metrics + Plotly
   web/text         fallback)              strict JSON        charts
```

**Reliability by design (objective 6):**
- **Model fallback chain** — if the primary model errors/rate-limits, the
  `LLMClient` automatically retries the next model
  (`llama-3.3-70b-versatile → llama-3.1-8b-instant` by default).
- **Offline degradation** — with no API key, every LLM step falls back to a
  dependency-free **extractive** summarizer / heuristic analyzer, so the whole
  pipeline still runs and can be demoed. Each step records `ok` vs `fallback`
  in the run trace.
- **Per-source isolation** — a failure loading one source is traced and
  skipped; the others still process.

---

## Quickstart (local)

```bash
cd multi_agent_system
python -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt

# run entirely offline (no key needed)
streamlit run app.py
```

Open http://localhost:8501 → **Sources** tab → **Load sample data** → **Run pipeline**.

To use a real LLM, pick a provider in the sidebar and paste a key
(get a free Groq key at <https://console.groq.com>), or set env vars from
`.env.example`.

---

## Deployment

### A) Streamlit + ngrok (recommended for the demo video)

```bash
export NGROK_AUTH_TOKEN=xxxxx          # from https://dashboard.ngrok.com
python run_ngrok.py
```
Prints a **PUBLIC URL** you can open from anywhere.

### B) Google Colab

Open `run_colab.ipynb` in Colab, upload/unzip the project, run the cells
(install → set keys → launch). The last cell prints the public ngrok URL.

### C) FastAPI (REST)

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
# optional public tunnel:  ngrok http 8000
```

```bash
# example call (offline mode)
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"sources":[{"kind":"text","text":"Cloud revenue grew 30% in 2026.","title":"note"}],
       "report_title":"API Brief","provider":"offline"}'
```
Endpoints: `GET /health`, `POST /run`, `POST /run-files` (upload PDFs/CSVs),
`GET /report.pdf`.

---

## Testing & evaluation

```bash
pytest -q                       # 10 unit + integration tests (all offline)
python evaluation/evaluate.py   # reliability / accuracy / efficiency report
```

The evaluator runs the full pipeline on the bundled sample corpus and prints
retrieval completeness, agent success rate, keyword-coverage & ground-truth
recall (accuracy proxies), per-agent latency, and a parallel-vs-serial speed
comparison, ending with PASS/FAIL gates.

---

## Project structure

```
multi_agent_system/
├── app.py                 # Streamlit UI (main entrypoint)
├── api.py                 # FastAPI REST deployment path
├── run_ngrok.py           # launch Streamlit + public ngrok tunnel
├── run_colab.ipynb        # Colab runner notebook
├── orchestrator.py        # coordinates all agents (sequential + parallel)
├── llm_client.py          # provider-agnostic LLM client + fallback chain
├── config.py              # env-driven settings
├── agents/
│   ├── base.py            # BaseAgent + Document model + timing/trace
│   ├── retrieval_agent.py # PDF/CSV/Sheet/API/web/text loaders
│   ├── summarizer_agent.py
│   ├── analysis_agent.py  # cross-source synthesis → strict JSON
│   ├── report_agent.py    # Markdown + PDF
│   ├── email_agent.py     # draft + optional SMTP send
│   └── dashboard_agent.py # metrics + chart data
├── utils/
│   ├── extractive.py      # offline summarizer/keyword fallback
│   └── logging_utils.py   # RunTrace / TraceEvent
├── evaluation/evaluate.py
├── tests/test_pipeline.py
├── sample_data/           # sample PDF + CSV
├── requirements.txt
├── .env.example
└── .streamlit/config.toml
```

---

## 🎬 Demo script (for the face-cam video — objective 5)

Keep it ~4–6 minutes:

1. **Problem (20s).** "Analysts waste hours pulling data from PDFs, sheets, and
   APIs, then summarizing and reporting by hand. This system automates that
   whole workflow with cooperating AI agents."
2. **Architecture (60s).** Show this README's diagram. Explain the four stages
   and *why summarization is parallel* (sources are independent, so it's the
   biggest time saving) while the rest is sequential (each stage needs the
   previous stage's output).
3. **Live run (120s).** In the app: load sample data (or upload your own PDF +
   CSV + a Google Sheet URL). Click **Run pipeline** and narrate the live
   progress bar as it moves through the stages.
4. **Outputs (90s).** Walk the tabs: **Report** (download the PDF),
   **Analysis** (findings/recommendations/sentiment), **Dashboard** (charts +
   metrics), **Email** (the drafted stakeholder email).
5. **Orchestration proof (40s).** Open the **Run Trace** tab — show the ordered
   list of agent steps with per-step latency and the success rate. This is the
   visible evidence of orchestration.
6. **Reliability (30s).** Toggle provider to **offline** and re-run to show the
   extractive fallback keeps everything working — then run `evaluate.py` and
   point at the PASS gates.
7. **Deployment (20s).** Show the public **ngrok URL** (or the FastAPI
   `/health` + `/run` call) to prove it's deployed, not just local.

---

## Notes & troubleshooting

- **Groq model names change over time.** If a model 404s, update
  `GROQ_PRIMARY_MODEL` / `GROQ_FALLBACK_MODEL` in `.env` to current Groq models.
- **ngrok now requires an auth token** even on the free tier — set
  `NGROK_AUTH_TOKEN`.
- **Google Sheets** must be shared publicly ("anyone with the link") for the
  CSV-export retrieval to work without OAuth.
- **PDF export** uses core Latin-1 fonts; non-Latin characters are replaced. For
  full Unicode, register a TTF font in `report_agent.py`.
- **Sending email** is off by default. It only sends when you fill the SMTP_*
  env vars *and* explicitly click send in the Email tab.
