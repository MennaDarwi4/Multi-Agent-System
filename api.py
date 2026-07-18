"""
FastAPI backend for Argus — Market & Competitive Intelligence.

The pipeline runs here; the Streamlit app (app.py) is a thin frontend that calls
these endpoints over HTTP. Groq is the only LLM provider and all configuration
is read from the environment / .env — nothing is passed from the client.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health   - liveness + whether a Groq key is configured
    POST /run      - multipart: uploaded PDF/CSV files + a JSON `payload`
                     describing the other sources and run options
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from collections import OrderedDict
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents import EmailAgent, QAAgent
from config import APP_NAME, Settings
from orchestrator import Orchestrator

app = FastAPI(title=f"{APP_NAME} — Market Intelligence API", version="2.0")

# In-memory context cache so "Ask Argus" can answer questions against a run's
# sources without re-retrieving them. Keyed by run_id; oldest entries evicted.
_CONTEXT_STORE: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()
_CONTEXT_MAX = 50


def _remember_context(docs) -> str:
    run_id = uuid.uuid4().hex
    _CONTEXT_STORE[run_id] = [
        {"title": d.title, "text": (d.text or "")[:6000]} for d in docs
    ]
    while len(_CONTEXT_STORE) > _CONTEXT_MAX:
        _CONTEXT_STORE.popitem(last=False)
    return run_id

# Optional shared-secret auth. When BACKEND_API_KEY is set (recommended for a
# public deployment) every request to /run and /send-email must send a matching
# `X-API-Key` header. Left unset, the guard is a no-op so local dev just works.
_API_KEY = os.getenv("BACKEND_API_KEY", "")


def require_key(x_api_key: str = Header(default="")) -> None:
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# --------------------------------------------------------------------------
# Serialization: turn a PipelineResult into JSON the frontend can render.
# --------------------------------------------------------------------------
def _serialize_dashboard(dash: Dict[str, Any]) -> Dict[str, Any]:
    if not dash:
        return {}
    out = {k: v for k, v in dash.items() if k != "tables"}
    tables = []
    for t in dash.get("tables", []):
        df = t.get("dataframe")
        records = df.to_dict(orient="records") if df is not None else []
        tables.append({"title": t.get("title", ""), "records": records})
    out["tables"] = tables
    return out


def _serialize(res) -> Dict[str, Any]:
    report = res.report or {}
    pdf_bytes = report.get("pdf_bytes")
    trace = res.trace
    return {
        "documents": [
            {"title": d.title, "type": d.source_type, "chars": d.char_count,
             "keywords": d.keywords, "summary": d.summary}
            for d in res.documents
        ],
        # drop internal helper keys (prefixed with "_top")
        "analysis": {k: v for k, v in res.analysis.items() if not k.startswith("_top")},
        "report": {
            "markdown": report.get("markdown", ""),
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else "",
        },
        "email": res.email or {},
        "dashboard": _serialize_dashboard(res.dashboard),
        "trace": {
            "rows": trace.as_rows() if trace else [],
            "events_count": len(trace.events) if trace else 0,
            "success_rate": trace.success_rate() if trace else 0.0,
            "total_latency_s": trace.total_latency_s if trace else 0.0,
        },
    }


# --------------------------------------------------------------------------
# Source assembly: uploaded files (kind inferred from extension) + JSON sources.
# --------------------------------------------------------------------------
async def _file_sources(files: List[UploadFile]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for f in files:
        data = await f.read()
        name = (f.filename or "file").lower()
        if name.endswith(".pdf"):
            sources.append({"kind": "pdf", "bytes": data, "title": f.filename})
        elif name.endswith((".csv", ".tsv")):
            sources.append({"kind": "csv", "bytes": data, "title": f.filename})
        else:
            sources.append({"kind": "text", "text": data.decode("utf-8", "ignore"),
                            "title": f.filename})
    return sources


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/health")
def health() -> Dict[str, Any]:
    s = Settings()
    return {"status": "ok", "provider": "groq", "llm_key_configured": s.has_llm_key()}


@app.post("/run", dependencies=[Depends(require_key)])
async def run(
    files: List[UploadFile] = File(default=[]),
    payload: str = Form("{}"),
) -> JSONResponse:
    opts = json.loads(payload or "{}")

    sources = await _file_sources(files)
    sources.extend(opts.get("sources", []))

    if not sources:
        return JSONResponse({"error": "No sources provided."}, status_code=400)

    orch = Orchestrator(Settings())
    res = orch.run(
        sources,
        report_title=opts.get("report_title", "Market Intelligence Brief"),
        objective=opts.get("objective", ""),
        max_sentences=int(opts.get("max_sentences", 5)),
        do_report=bool(opts.get("do_report", True)),
        do_email=bool(opts.get("do_email", True)),
        do_dashboard=bool(opts.get("do_dashboard", True)),
        email_recipient=opts.get("email_recipient", "the team"),
    )
    out = _serialize(res)
    out["run_id"] = _remember_context(res.documents)
    return JSONResponse(out)


class AskRequest(BaseModel):
    run_id: str
    question: str


@app.post("/ask", dependencies=[Depends(require_key)])
def ask(req: AskRequest) -> JSONResponse:
    """Answer a question grounded in the sources of a previous /run."""
    context = _CONTEXT_STORE.get(req.run_id)
    if context is None:
        return JSONResponse(
            {"error": "No analyzed sources found for this session. Run Argus first."},
            status_code=404,
        )
    return JSONResponse(QAAgent().answer(req.question, context))


class SendEmailRequest(BaseModel):
    to_addr: str
    subject: str
    body: str


@app.post("/send-email", dependencies=[Depends(require_key)])
def send_email(req: SendEmailRequest) -> JSONResponse:
    """Send a drafted email via SMTP (requires SMTP_* env vars on the server)."""
    status = EmailAgent().send(req.to_addr, req.subject, req.body)
    return JSONResponse(status)
