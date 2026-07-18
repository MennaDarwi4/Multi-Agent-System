# 🛰️ Argus — Market & Competitive Intelligence

> *Your market, watched.*

**Argus** turns scattered market signals — competitor web pages, market reports
(PDF), metrics (CSV), and news/market APIs — into a **decision-ready
intelligence brief**: an executive read of the competitive landscape (market
trends, competitor moves, opportunities, threats), a **stakeholder email**, and
a **live dashboard**. A team of coordinated agents retrieves, summarizes in
parallel, synthesizes, and acts.

Two processes: a **FastAPI** backend that runs the pipeline and a **Streamlit**
frontend that calls it over HTTP. LLM calls go to the **Groq API**.

---

## How it maps to the project objectives

| # | Objective | Where it lives |
|---|-----------|----------------|
| 1 | **Data Retrieval** (PDF, Sheets, APIs, DBs) | `agents/retrieval_agent.py` — PDF, CSV/TSV, public Google Sheets, JSON APIs, web pages, raw text |
| 2 | **Processing & Summarization** with LLMs | `agents/summarizer_agent.py` (per-source) + `agents/analysis_agent.py` (competitive-landscape synthesis → structured JSON: trends, competitor moves, opportunities, threats) |
| 3 | **Automated Actions** (emails, reports, dashboards) | `agents/report_agent.py` (Markdown + PDF), `agents/email_agent.py` (draft + optional SMTP send), `agents/dashboard_agent.py` (metrics + charts) |
| 4 | **Workflow Orchestration** (sequential + parallel) | `orchestrator.py` — sequential stages with a **parallel** summarization stage (thread pool) |
| 5 | **Presentation & Explanation** | `api.py` (FastAPI backend) + `app.py` (Streamlit frontend with a live run trace) + the *Demo script* below |
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
- **Offline degradation** — with no Groq API key, every LLM step falls back to a
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

# add your Groq key (or leave it blank to run with extractive fallbacks)
cp .env.example .env      # then edit GROQ_API_KEY

# start the backend + frontend together
python run.py
```

Or run the two processes yourself in separate terminals:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000    # backend (pipeline + LLM)
streamlit run app.py                          # frontend (UI)
```

Open http://localhost:8501 → **Sources** tab → **Load sample data** → **Run pipeline**.

**Architecture:** the Streamlit frontend never touches the LLM. It POSTs staged
sources to the FastAPI backend (`POST /run`), which runs the orchestrator and
returns JSON (report markdown + base64 PDF, analysis, dashboard data, email
draft, run trace). The frontend finds the backend via `BACKEND_URL`
(default `http://localhost:8000`).

Configuration (Groq key, models, generation params, SMTP) is read entirely from
the **backend's** environment / `.env` — there are no settings in the UI. Get a
free Groq key at <https://console.groq.com>. Without a key the pipeline still
runs using the extractive fallbacks.

### Backend endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | Liveness + whether a Groq key is configured |
| `POST` | `/run` | Multipart: uploaded PDF/CSV `files` + a JSON `payload` (other sources + run options) → full pipeline result as JSON |
| `POST` | `/send-email` | Send a drafted email via SMTP (requires `SMTP_*` on the backend) |

---

## Deployment (Streamlit Cloud frontend + hosted backend)

The two processes deploy separately. The **backend** runs as a Docker service on
a host that can hold a long-running process (Render/Railway/Fly); the
**frontend** runs on Streamlit Community Cloud and points at the backend's
public URL.

### 1 · Deploy the backend (Render, via `render.yaml`)

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → pick the repo. It builds the `Dockerfile` and
   runs `uvicorn api:app`.
3. In the service's **Environment**, set:
   - `GROQ_API_KEY` — your Groq key.
   - `BACKEND_API_KEY` — a long random string (shared secret with the frontend).
4. After it goes live, note the public URL, e.g.
   `https://multi-agent-backend.onrender.com`. Check `…/health` returns
   `{"status":"ok",...}`.

*(Railway/Fly work the same way — they build the `Dockerfile` and inject `$PORT`,
which the image already honors.)*

### 2 · Deploy the frontend (Streamlit Community Cloud)

1. <https://share.streamlit.io> → **New app** → this repo → main file `app.py`.
2. **Advanced settings → Secrets**: paste the values from
   [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example):
   ```toml
   BACKEND_URL = "https://multi-agent-backend.onrender.com"
   BACKEND_API_KEY = "same-random-string-as-the-backend"
   BACKEND_TIMEOUT = "600"
   ```
3. Deploy. The app reads these via `st.secrets` (falling back to env vars), shows
   a 🟢 *Backend connected* banner when it reaches the backend, and sends
   `X-API-Key` on every call.

### Notes

- **No CORS needed** — the frontend calls the backend server-to-server (Python
  `requests`), not from the browser.
- **Free tiers sleep.** Render's free service spins down when idle; the first
  request after a nap is slow (cold start). The health banner will show the
  backend as down until it wakes.
- **Long runs.** `POST /run` is synchronous, so a big batch holds the connection
  open (`BACKEND_TIMEOUT` covers the client side). For heavier use, switch to an
  async job endpoint (`POST /run` → id, poll `GET /run/{id}`).
- **Keep the backend private-ish.** Always set `BACKEND_API_KEY` in production so
  a public URL can't be used to burn your Groq quota.

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
├── api.py                 # FastAPI backend (runs the pipeline, serves JSON)
├── app.py                 # Streamlit frontend (calls the backend over HTTP)
├── run.py                 # launches backend + frontend together
├── orchestrator.py        # coordinates all agents (sequential + parallel)
├── llm_client.py          # Groq LLM client + model fallback chain
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
   CSV + a Google Sheet URL). Click **Run pipeline** — the frontend POSTs to the
   FastAPI backend, which runs the agents and returns the result as JSON.
4. **Outputs (90s).** Walk the tabs: **Report** (download the PDF),
   **Analysis** (findings/recommendations/sentiment), **Dashboard** (charts +
   metrics), **Email** (the drafted stakeholder email).
5. **Orchestration proof (40s).** Open the **Run Trace** tab — show the ordered
   list of agent steps with per-step latency and the success rate. This is the
   visible evidence of orchestration.
6. **Reliability (30s).** Unset `GROQ_API_KEY` and re-run to show the extractive
   fallback keeps everything working — then run `evaluate.py` and point at the
   PASS gates.

---

## Notes & troubleshooting

- **Groq model names change over time.** If a model 404s, update
  `GROQ_PRIMARY_MODEL` / `GROQ_FALLBACK_MODEL` in `.env` to current Groq models.
- **Google Sheets** must be shared publicly ("anyone with the link") for the
  CSV-export retrieval to work without OAuth.
- **PDF export** uses core Latin-1 fonts; non-Latin characters are replaced. For
  full Unicode, register a TTF font in `report_agent.py`.
- **Sending email** is off by default. It only sends when you fill the SMTP_*
  env vars *and* explicitly click send in the Email tab.
