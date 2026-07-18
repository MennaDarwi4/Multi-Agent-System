"""
FastAPI deployment path (alternative to Streamlit).

Exposes the same multi-agent pipeline as a REST API so it can be automated /
called by other services.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000
    # optional public tunnel:
    #   ngrok http 8000

Endpoints:
    GET  /health
    POST /run        - JSON body with text/api/web/sheet sources
    POST /run-files  - multipart upload of PDF/CSV files
    GET  /report.pdf - download the PDF from the last /run (in-memory, demo only)
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from config import Settings
from orchestrator import Orchestrator

app = FastAPI(title="Multi-Agent AI System API", version="1.0")

# tiny in-memory store for the last PDF (demo convenience only)
_LAST_PDF: Dict[str, bytes] = {}


class SourceIn(BaseModel):
    kind: str                      # text | api | web | sheet
    text: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None


class RunRequest(BaseModel):
    sources: List[SourceIn]
    report_title: str = "Automated Intelligence Report"
    objective: str = ""
    provider: str = "offline"      # offline | groq | openai | anthropic
    api_key: str = ""
    max_sentences: int = 5


def _settings(provider: str, api_key: str) -> Settings:
    s = Settings()
    s.provider = provider
    if provider == "groq":
        s.groq_api_key = api_key
    elif provider == "openai":
        s.openai_api_key = api_key
    elif provider == "anthropic":
        s.anthropic_api_key = api_key
    return s


def _serialize(res) -> Dict[str, Any]:
    if res.report.get("pdf_bytes"):
        _LAST_PDF["pdf"] = res.report["pdf_bytes"]
    return {
        "documents": [
            {"title": d.title, "type": d.source_type, "chars": d.char_count,
             "keywords": d.keywords, "summary": d.summary}
            for d in res.documents
        ],
        "analysis": {k: v for k, v in res.analysis.items() if not k.startswith("_top")},
        "email": res.email,
        "report_markdown": res.report.get("markdown", ""),
        "report_pdf_available": bool(res.report.get("pdf_bytes")),
        "dashboard_metrics": res.dashboard.get("metrics", {}),
        "trace": res.trace.as_rows() if res.trace else [],
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run(req: RunRequest) -> JSONResponse:
    sources = [
        {k: v for k, v in s.model_dump().items() if v is not None}
        for s in req.sources
    ]
    orch = Orchestrator(_settings(req.provider, req.api_key))
    res = orch.run(sources, report_title=req.report_title,
                   objective=req.objective, max_sentences=req.max_sentences)
    return JSONResponse(_serialize(res))


@app.post("/run-files")
async def run_files(
    files: List[UploadFile] = File(default=[]),
    report_title: str = Form("Automated Intelligence Report"),
    objective: str = Form(""),
    provider: str = Form("offline"),
    api_key: str = Form(""),
) -> JSONResponse:
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
    orch = Orchestrator(_settings(provider, api_key))
    res = orch.run(sources, report_title=report_title, objective=objective)
    return JSONResponse(_serialize(res))


@app.get("/report.pdf")
def report_pdf() -> Response:
    pdf = _LAST_PDF.get("pdf")
    if not pdf:
        return JSONResponse({"error": "No report generated yet."}, status_code=404)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=report.pdf"})
