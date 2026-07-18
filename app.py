"""
Argus — Market & Competitive Intelligence · Streamlit frontend  (Objective 5)

This is a thin UI. The pipeline runs in the FastAPI backend (api.py); this app
only stages sources, POSTs them to the backend, and renders the JSON response.

Run the backend first, then this app:
    uvicorn api:app --port 8000
    streamlit run app.py

The backend URL is read from BACKEND_URL (default http://localhost:8000).
Configuration (Groq API key, models, generation params) lives on the backend's
environment / .env — there are no settings in the UI.
"""
from __future__ import annotations

import base64
import json
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from config import APP_DESCRIPTION, APP_NAME, APP_TAGLINE


def _conf(name: str, default: str = "") -> str:
    """Read config from env first, then Streamlit secrets (for Streamlit Cloud)."""
    val = os.getenv(name)
    if val:
        return val
    try:
        return str(st.secrets[name])
    except Exception:  # no secrets file / key not present
        return default


BACKEND_URL = _conf("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = int(_conf("BACKEND_TIMEOUT", "600"))
BACKEND_API_KEY = _conf("BACKEND_API_KEY", "")
_AUTH_HEADERS = {"X-API-Key": BACKEND_API_KEY} if BACKEND_API_KEY else {}

# --------------------------------------------------------------------------
# Page config + light theming
# --------------------------------------------------------------------------
st.set_page_config(
    page_title=f"{APP_NAME} — Market Intelligence",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .main .block-container {padding-top: 2rem; max-width: 1200px;}
    .agent-badge {display:inline-block; padding:2px 10px; border-radius:12px;
        background:#1f6feb22; color:#1f6feb; font-size:0.8rem; margin-right:6px;}
    .metric-card {background:#0e1117; border:1px solid #262730; border-radius:12px;
        padding:14px 18px;}
    h1, h2, h3 {letter-spacing:-0.01em;}
    .stAlert {border-radius:10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
if "sources" not in st.session_state:
    st.session_state.sources = []          # staged source dicts
if "result" not in st.session_state:
    st.session_state.result = None         # last PipelineResult
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0      # bump to reset the file uploaders
if "chat" not in st.session_state:
    st.session_state.chat = []             # Ask Argus history: {role, content}
if "chat_run_id" not in st.session_state:
    st.session_state.chat_run_id = None    # resets chat when a new run happens


# --------------------------------------------------------------------------
# Backend client — the pipeline runs in the FastAPI backend (api.py).
# --------------------------------------------------------------------------
# Default summary length (previously an "Advanced settings" slider).
max_sentences = 5


def _split_sources(sources: list) -> tuple[list, list]:
    """Separate binary file sources (sent as multipart) from JSON sources."""
    files, json_sources = [], []
    for s in sources:
        if "bytes" in s:
            files.append(("files", (s.get("title", "file"), s["bytes"], "application/octet-stream")))
        else:
            json_sources.append({k: v for k, v in s.items() if k != "bytes"})
    return files, json_sources


def run_pipeline(sources: list, **opts) -> dict:
    """POST staged sources + options to the backend and return the parsed JSON."""
    files, json_sources = _split_sources(sources)
    payload = {"sources": json_sources, **opts}
    resp = requests.post(
        f"{BACKEND_URL}/run",
        files=files,
        data={"payload": json.dumps(payload)},
        headers=_AUTH_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.title(f"🛰️ {APP_NAME}")
st.markdown(f"### {APP_TAGLINE}")
st.markdown(
    f"{APP_DESCRIPTION} Feed **competitor pages, market reports (PDF), metrics "
    "(CSV), and news APIs** — a team of coordinated agents **summarizes, "
    "analyzes the landscape, and acts**, producing a market brief, a stakeholder "
    "email, and a live dashboard."
)


@st.cache_data(ttl=10, show_spinner=False)
def _backend_health() -> dict:
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": str(e)}


_health = _backend_health()
if _health.get("status") != "ok":
    st.error("⚠️ The analysis service is temporarily unavailable. "
             "Please try again in a moment.")

tab_sources, tab_report, tab_dash, tab_ask, tab_email = st.tabs(
    ["📥 Signals", "📄 Brief", "📊 Dashboard", "💬 Ask", "✉️ Email"]
)

# --------------------------------------------------------------------------
# TAB: Sources
# --------------------------------------------------------------------------
with tab_sources:
    st.subheader("1 · Add market signals")

    def _stage_uploads(files, kind: str) -> None:
        """Auto-stage uploaded files (no extra click), deduped by name."""
        existing = {(s["kind"], s["title"]) for s in st.session_state.sources
                    if "bytes" in s}
        for f in files or []:
            key = (kind, f.name)
            if key not in existing:
                st.session_state.sources.append(
                    {"kind": kind, "bytes": f.getvalue(), "title": f.name}
                )
                existing.add(key)

    c1, c2 = st.columns(2)

    with c1:
        uk = st.session_state.uploader_key
        up_pdfs = st.file_uploader("Market report(s) — PDF", type=["pdf"],
                                   accept_multiple_files=True, key=f"pdf_{uk}")
        _stage_uploads(up_pdfs, "pdf")

        up_csvs = st.file_uploader("Metrics / sales — CSV/TSV", type=["csv", "tsv"],
                                   accept_multiple_files=True, key=f"csv_{uk}")
        _stage_uploads(up_csvs, "csv")

        sheet_url = st.text_input("Public Google Sheet URL")
        if sheet_url and st.button("➕ Add Google Sheet"):
            st.session_state.sources.append(
                {"kind": "sheet", "url": sheet_url, "title": "Google Sheet"}
            )
            st.success("Added Google Sheet.")

    with c2:
        web_url = st.text_input("Competitor / market web page URL")
        if web_url and st.button("➕ Add web page"):
            st.session_state.sources.append(
                {"kind": "web", "url": web_url, "title": web_url}
            )
            st.success("Added web page.")

        api_url = st.text_input("News / market API URL (returns JSON)")
        if api_url and st.button("➕ Add API"):
            st.session_state.sources.append(
                {"kind": "api", "url": api_url, "title": f"API: {api_url[:30]}"}
            )
            st.success("Added API source.")

        paste = st.text_area("Paste raw text (notes, transcripts, snippets)", height=90)
        if paste and st.button("➕ Add pasted text"):
            st.session_state.sources.append(
                {"kind": "text", "text": paste, "title": "Pasted text"}
            )
            st.success("Added text source.")

    st.divider()
    n_sources = len(st.session_state.sources)
    if n_sources:
        cs1, cs2 = st.columns([3, 1])
        cs1.success(f"✅ {n_sources} source(s) staged — ready to run.")
        if cs2.button("🗑️ Clear all"):
            st.session_state.sources = []
            st.session_state.result = None
            st.session_state.uploader_key += 1   # reset the file uploaders
            st.rerun()
    else:
        st.info("Add at least one source above — a single file is enough to run.")

    st.divider()
    st.subheader("2 · Configure & run")
    report_title = st.text_input("Brief title", "Market Intelligence Brief")
    objective = st.text_input(
        "Intelligence objective (optional)",
        "Assess the competitive landscape: key players, positioning, momentum, "
        "opportunities, and threats",
    )
    a1, a2, a3 = st.columns(3)
    do_report = a1.checkbox("Generate brief", True)
    do_email = a2.checkbox("Draft email", True)
    do_dashboard = a3.checkbox("Build dashboard", True)
    email_recipient = st.text_input("Email recipient (label)", "the team")

    run = st.button(f"🛰️ Run {APP_NAME}", type="primary", use_container_width=True,
                    disabled=not st.session_state.sources)

    if run:
        try:
            with st.spinner("Running pipeline on the backend…"):
                st.session_state.result = run_pipeline(
                    st.session_state.sources,
                    report_title=report_title,
                    objective=objective,
                    max_sentences=max_sentences,
                    do_report=do_report,
                    do_email=do_email,
                    do_dashboard=do_dashboard,
                    email_recipient=email_recipient,
                )
            st.success("Done — see the Brief, Landscape, Dashboard, and Email tabs.")
        except requests.HTTPError as e:  # noqa: BLE001
            detail = ""
            try:
                detail = e.response.json().get("error", "")
            except Exception:  # noqa: BLE001
                detail = e.response.text[:300] if e.response is not None else ""
            st.error(f"Pipeline failed ({e}). {detail}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Pipeline failed: {e}")


result = st.session_state.result

# --------------------------------------------------------------------------
# TAB: Report
# --------------------------------------------------------------------------
with tab_report:
    report = (result or {}).get("report") if result else None
    if report and report.get("markdown"):
        st.subheader("Market intelligence brief")

        analysis = (result or {}).get("analysis") or {}
        if analysis:
            sentiment = analysis.get("overall_sentiment", "neutral")
            color = {"positive": "🟢", "negative": "🔴"}.get(sentiment, "🟡")
            s1, s2 = st.columns(2)
            s1.metric("Market sentiment", f"{color} {sentiment}")
            s2.metric("Confidence", analysis.get("confidence", "n/a"))

        md = report.get("markdown", "")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Download Markdown", md, file_name="market_brief.md",
                           mime="text/markdown", use_container_width=True)
        if report.get("pdf_base64"):
            d2.download_button("⬇️ Download PDF", base64.b64decode(report["pdf_base64"]),
                               file_name="market_brief.pdf", mime="application/pdf",
                               use_container_width=True)
        st.markdown("---")
        st.markdown(md)
    else:
        st.info("Run Argus to generate a market brief.")

# --------------------------------------------------------------------------
# TAB: Dashboard
# --------------------------------------------------------------------------
with tab_dash:
    d = (result or {}).get("dashboard") if result else None
    if d and d.get("metrics"):
        m = d["metrics"]
        sentiment = m.get("sentiment", "neutral")
        color = {"positive": "🟢", "negative": "🔴"}.get(sentiment, "🟡")
        st.subheader("Market overview")
        cols = st.columns(3)
        cols[0].metric("Signals analyzed", m["sources"])
        cols[1].metric("Market sentiment", f"{color} {sentiment}")
        cols[2].metric("Confidence", m.get("confidence", "n/a"))

        g1, g2 = st.columns(2)
        with g1:
            if d.get("source_type_counts"):
                fig = px.pie(
                    names=list(d["source_type_counts"].keys()),
                    values=list(d["source_type_counts"].values()),
                    title="Signals by type", hole=0.45,
                )
                st.plotly_chart(fig, use_container_width=True)
        with g2:
            if d.get("top_keywords"):
                st.markdown("#### 🔥 Trending topics")
                st.write(" ".join(f"`{k}`" for k in d["top_keywords"]))

        # chart any numeric columns from an uploaded metrics/sales table
        for t in d.get("tables", []):
            records = t.get("records") or []
            if records:
                df = pd.DataFrame(records)
                num = df.select_dtypes("number")
                if not num.empty:
                    st.markdown(f"#### 📊 {t['title']}")
                    fig = px.line(num.reset_index(), x="index", y=list(num.columns),
                                  markers=True, title=t["title"])
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Run Argus to build the market dashboard.")

# --------------------------------------------------------------------------
# TAB: Ask Argus  (interactive Q&A grounded in the run's sources)
# --------------------------------------------------------------------------
with tab_ask:
    run_id = (result or {}).get("run_id") if result else None
    if not run_id:
        st.info("Run Argus first, then ask questions about your market signals.")
    else:
        # reset the conversation whenever a fresh run happens
        if st.session_state.chat_run_id != run_id:
            st.session_state.chat = []
            st.session_state.chat_run_id = run_id

        st.caption("Ask anything about the sources you just analyzed — answers are "
                   "grounded in those sources.")
        for msg in st.session_state.chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        question = st.chat_input("e.g. What are the biggest threats to our position?")
        if question:
            st.session_state.chat.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    try:
                        r = requests.post(
                            f"{BACKEND_URL}/ask",
                            json={"run_id": run_id, "question": question},
                            headers=_AUTH_HEADERS,
                            timeout=120,
                        )
                        r.raise_for_status()
                        answer = r.json().get("answer", "—")
                    except Exception as e:  # noqa: BLE001
                        answer = f"Couldn't answer right now: {e}"
                st.markdown(answer)
            st.session_state.chat.append({"role": "assistant", "content": answer})

# --------------------------------------------------------------------------
# TAB: Email
# --------------------------------------------------------------------------
with tab_email:
    email = (result or {}).get("email") if result else None
    if email:
        st.subheader("Stakeholder email")
        subject = st.text_input("Subject", email.get("subject", ""))
        body = st.text_area("Body", email.get("body", ""), height=280)
        st.download_button("⬇️ Download .eml", f"Subject: {subject}\n\n{body}",
                           file_name="draft.eml", mime="message/rfc822")

        st.divider()
        st.caption("Send this brief to a colleague:")
        to_addr = st.text_input("Recipient email address")
        if st.button("📤 Send email", disabled=not to_addr):
            try:
                r = requests.post(
                    f"{BACKEND_URL}/send-email",
                    json={"to_addr": to_addr, "subject": subject, "body": body},
                    headers=_AUTH_HEADERS,
                    timeout=60,
                )
                r.raise_for_status()
                status = r.json()
                if status.get("sent"):
                    st.success(f"Sent to {to_addr}")
                else:
                    st.warning(f"Not sent: {status.get('reason')}")
            except Exception as e:  # noqa: BLE001
                st.error(f"Send failed: {e}")
    else:
        st.info("Run the pipeline to draft an email.")
