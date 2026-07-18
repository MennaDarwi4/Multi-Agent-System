"""
Multi-Agent AI System - Streamlit UI  (Objective 5: Presentation)

Run locally:
    streamlit run app.py

Run on Colab / expose publicly with ngrok:
    python run_ngrok.py            (see that file / README)

The UI lets you stage heterogeneous sources, run the orchestrated pipeline with
a live progress bar, and inspect every output: report, structured analysis,
an auto dashboard, the drafted email, and the full orchestration trace.
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from config import Settings
from orchestrator import Orchestrator

# --------------------------------------------------------------------------
# Page config + light theming
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Multi-Agent AI System",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
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


# --------------------------------------------------------------------------
# Sidebar: configuration
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    _providers = ["offline", "groq", "openai", "anthropic"]
    _default_provider = os.getenv("LLM_PROVIDER", "offline").lower()
    provider = st.selectbox(
        "LLM provider",
        _providers,
        index=_providers.index(_default_provider) if _default_provider in _providers else 0,
        help="Choose 'offline' to run the whole pipeline with extractive "
             "fallbacks (no key needed). Pick a provider + paste a key for real "
             "LLM summarization and analysis.",
    )

    api_key = ""
    if provider != "offline":
        api_key = st.text_input(
            f"{provider.upper()} API key",
            type="password",
            value=os.getenv(f"{provider.upper()}_API_KEY", ""),
            help="Kept only in this session; never written to disk.",
        )

    with st.expander("Advanced settings"):
        temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1)
        max_tokens = st.number_input("Max tokens", 256, 4096, 1024, 128)
        parallel_workers = st.slider("Parallel summarizer workers", 1, 8, 4)
        max_sentences = st.slider("Summary length (sentences)", 2, 10, 5)

    st.divider()
    st.caption("Pipeline: Retrieve → Summarize (∥) → Analyze → "
               "Report / Email / Dashboard")


def build_settings() -> Settings:
    s = Settings()
    s.provider = provider
    if provider == "groq":
        s.groq_api_key = api_key
    elif provider == "openai":
        s.openai_api_key = api_key
    elif provider == "anthropic":
        s.anthropic_api_key = api_key
    s.temperature = temperature
    s.max_tokens = int(max_tokens)
    s.parallel_workers = int(parallel_workers)
    return s


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.title("🧠 Multi-Agent AI System")
st.markdown(
    "Retrieve data from **PDFs, CSVs, Google Sheets, APIs, and web pages**, "
    "then let a team of coordinated agents **summarize, analyze, and act** — "
    "producing a report, an email draft, and a live dashboard."
)

tab_sources, tab_report, tab_analysis, tab_dash, tab_email, tab_trace = st.tabs(
    ["📥 Sources", "📄 Report", "🔎 Analysis", "📊 Dashboard", "✉️ Email", "🧭 Run Trace"]
)

# --------------------------------------------------------------------------
# TAB: Sources
# --------------------------------------------------------------------------
with tab_sources:
    st.subheader("1 · Add data sources")
    c1, c2 = st.columns(2)

    with c1:
        up_pdfs = st.file_uploader("Upload PDF(s)", type=["pdf"], accept_multiple_files=True)
        if up_pdfs and st.button("➕ Add uploaded PDFs"):
            for f in up_pdfs:
                st.session_state.sources.append(
                    {"kind": "pdf", "bytes": f.getvalue(), "title": f.name}
                )
            st.success(f"Added {len(up_pdfs)} PDF(s).")

        up_csvs = st.file_uploader("Upload CSV/TSV", type=["csv", "tsv"], accept_multiple_files=True)
        if up_csvs and st.button("➕ Add uploaded CSVs"):
            for f in up_csvs:
                st.session_state.sources.append(
                    {"kind": "csv", "bytes": f.getvalue(), "title": f.name}
                )
            st.success(f"Added {len(up_csvs)} table(s).")

        sheet_url = st.text_input("Public Google Sheet URL")
        if sheet_url and st.button("➕ Add Google Sheet"):
            st.session_state.sources.append(
                {"kind": "sheet", "url": sheet_url, "title": "Google Sheet"}
            )
            st.success("Added Google Sheet.")

    with c2:
        api_url = st.text_input("API URL (returns JSON)")
        if api_url and st.button("➕ Add API"):
            st.session_state.sources.append(
                {"kind": "api", "url": api_url, "title": f"API: {api_url[:30]}"}
            )
            st.success("Added API source.")

        web_url = st.text_input("Web page URL")
        if web_url and st.button("➕ Add web page"):
            st.session_state.sources.append(
                {"kind": "web", "url": web_url, "title": web_url}
            )
            st.success("Added web page.")

        paste = st.text_area("Paste raw text", height=90)
        if paste and st.button("➕ Add pasted text"):
            st.session_state.sources.append(
                {"kind": "text", "text": paste, "title": "Pasted text"}
            )
            st.success("Added text source.")

    st.divider()
    lc, rc = st.columns([3, 1])
    with lc:
        st.markdown("**Staged sources**")
        if st.session_state.sources:
            st.dataframe(
                pd.DataFrame(
                    [{"kind": s["kind"], "title": s.get("title", s.get("url", ""))}
                     for s in st.session_state.sources]
                ),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No sources yet. Add some above, or load the bundled samples →")
    with rc:
        if st.button("📦 Load sample data"):
            base = os.path.join(os.path.dirname(__file__), "sample_data")
            try:
                with open(os.path.join(base, "sample_market_memo.pdf"), "rb") as f:
                    st.session_state.sources.append(
                        {"kind": "pdf", "bytes": f.read(), "title": "sample_market_memo.pdf"})
                with open(os.path.join(base, "sample_sales.csv"), "rb") as f:
                    st.session_state.sources.append(
                        {"kind": "csv", "bytes": f.read(), "title": "sample_sales.csv"})
                st.session_state.sources.append(
                    {"kind": "text", "title": "analyst_note",
                     "text": "DevOps and SRE hiring in Egypt accelerated in 2026 with "
                             "strong Jenkins and Kubernetes demand."})
                st.success("Loaded 3 sample sources.")
            except Exception as e:
                st.error(f"Could not load samples: {e}")
        if st.button("🗑️ Clear all"):
            st.session_state.sources = []
            st.session_state.result = None

    st.divider()
    st.subheader("2 · Configure & run")
    report_title = st.text_input("Report title", "Automated Intelligence Report")
    objective = st.text_input("Analysis objective (optional)",
                              "Summarize the key findings and recommend next steps")
    a1, a2, a3 = st.columns(3)
    do_report = a1.checkbox("Generate report", True)
    do_email = a2.checkbox("Draft email", True)
    do_dashboard = a3.checkbox("Build dashboard", True)
    email_recipient = st.text_input("Email recipient (label)", "the team")

    run = st.button("🚀 Run pipeline", type="primary", use_container_width=True,
                    disabled=not st.session_state.sources)

    if run:
        prog = st.progress(0.0, text="Starting…")

        def cb(label, frac):
            prog.progress(min(frac, 1.0), text=label)

        try:
            orch = Orchestrator(build_settings())
            st.session_state.result = orch.run(
                st.session_state.sources,
                report_title=report_title,
                objective=objective,
                max_sentences=max_sentences,
                do_report=do_report,
                do_email=do_email,
                do_dashboard=do_dashboard,
                email_recipient=email_recipient,
                progress_cb=cb,
            )
            prog.progress(1.0, text="Done")
            st.success("Pipeline complete — see the Report, Analysis, Dashboard, "
                       "Email, and Run Trace tabs.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Pipeline failed: {e}")


result = st.session_state.result

# --------------------------------------------------------------------------
# TAB: Report
# --------------------------------------------------------------------------
with tab_report:
    if result and result.report:
        st.subheader("Generated report")
        md = result.report.get("markdown", "")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Download Markdown", md, file_name="report.md",
                           mime="text/markdown", use_container_width=True)
        if result.report.get("pdf_bytes"):
            d2.download_button("⬇️ Download PDF", result.report["pdf_bytes"],
                               file_name="report.pdf", mime="application/pdf",
                               use_container_width=True)
        st.markdown("---")
        st.markdown(md)
    else:
        st.info("Run the pipeline to generate a report.")

# --------------------------------------------------------------------------
# TAB: Analysis
# --------------------------------------------------------------------------
with tab_analysis:
    if result and result.analysis:
        a = result.analysis
        st.subheader("Cross-source synthesis")
        sentiment = a.get("overall_sentiment", "neutral")
        color = {"positive": "🟢", "negative": "🔴"}.get(sentiment, "🟡")
        m1, m2, m3 = st.columns(3)
        m1.metric("Sentiment", f"{color} {sentiment}")
        m2.metric("Confidence", a.get("confidence", "n/a"))
        m3.metric("Engine", a.get("_engine", "n/a"))

        st.markdown("#### Executive summary")
        st.write(a.get("executive_summary", "—"))

        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown("#### Key findings")
            for f in a.get("key_findings", []):
                st.markdown(f"- {f}")
        with cc2:
            st.markdown("#### Recommendations")
            for r in a.get("recommendations", []):
                st.markdown(f"- {r}")
        st.markdown("#### Risks & gaps")
        for r in a.get("risks_or_gaps", []):
            st.markdown(f"- {r}")
    else:
        st.info("Run the pipeline to see the analysis.")

# --------------------------------------------------------------------------
# TAB: Dashboard
# --------------------------------------------------------------------------
with tab_dash:
    if result and result.dashboard:
        d = result.dashboard
        m = d["metrics"]
        st.subheader("Live metrics")
        cols = st.columns(4)
        cols[0].metric("Sources", m["sources"])
        cols[1].metric("Success rate", f"{m['success_rate']*100:.0f}%")
        cols[2].metric("Compression", f"{m['compression_ratio']*100:.0f}%")
        cols[3].metric("Wall clock", f"{m['wall_clock_s']}s")

        g1, g2 = st.columns(2)
        with g1:
            if d.get("source_type_counts"):
                fig = px.pie(
                    names=list(d["source_type_counts"].keys()),
                    values=list(d["source_type_counts"].values()),
                    title="Sources by type", hole=0.45,
                )
                st.plotly_chart(fig, use_container_width=True)
        with g2:
            if d.get("agent_latency"):
                fig = px.bar(
                    x=list(d["agent_latency"].keys()),
                    y=list(d["agent_latency"].values()),
                    title="Latency per agent (s)", labels={"x": "", "y": "seconds"},
                )
                st.plotly_chart(fig, use_container_width=True)

        g3, g4 = st.columns(2)
        with g3:
            if d.get("chars_per_source"):
                fig = px.bar(
                    x=list(d["chars_per_source"].values()),
                    y=list(d["chars_per_source"].keys()),
                    orientation="h", title="Characters per source",
                    labels={"x": "chars", "y": ""},
                )
                st.plotly_chart(fig, use_container_width=True)
        with g4:
            if d.get("top_keywords"):
                st.markdown("#### Top keywords")
                st.write(" ".join(f"`{k}`" for k in d["top_keywords"]))

        # optional: chart from an uploaded numeric table
        for t in d.get("tables", []):
            df = t.get("dataframe")
            if isinstance(df, pd.DataFrame):
                num = df.select_dtypes("number")
                if not num.empty:
                    st.markdown(f"#### Numeric view · {t['title']}")
                    fig = px.line(num.reset_index(), x="index", y=list(num.columns),
                                  markers=True, title=t["title"])
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Run the pipeline to build the dashboard.")

# --------------------------------------------------------------------------
# TAB: Email
# --------------------------------------------------------------------------
with tab_email:
    if result and result.email:
        st.subheader("Drafted email (automated action)")
        subject = st.text_input("Subject", result.email.get("subject", ""))
        body = st.text_area("Body", result.email.get("body", ""), height=280)
        st.download_button("⬇️ Download .eml", f"Subject: {subject}\n\n{body}",
                           file_name="draft.eml", mime="message/rfc822")

        st.divider()
        st.caption("Optional: actually send via SMTP (requires SMTP_* env vars). "
                   "Sending is off by default so nothing is emailed by accident.")
        to_addr = st.text_input("Send to (email address)")
        if st.button("📤 Send email", disabled=not to_addr):
            from agents import EmailAgent
            status = EmailAgent().send(to_addr, subject, body)
            if status.get("sent"):
                st.success(f"Sent to {to_addr}")
            else:
                st.warning(f"Not sent: {status.get('reason')}")
    else:
        st.info("Run the pipeline to draft an email.")

# --------------------------------------------------------------------------
# TAB: Run Trace  (proof of orchestration)
# --------------------------------------------------------------------------
with tab_trace:
    if result and result.trace:
        st.subheader("Orchestration trace")
        st.caption("Every agent step, in execution order, with status and latency.")
        st.dataframe(pd.DataFrame(result.trace.as_rows()),
                     use_container_width=True, hide_index=True)
        t1, t2, t3 = st.columns(3)
        t1.metric("Agent steps", len(result.trace.events))
        t2.metric("Success rate", f"{result.trace.success_rate()*100:.0f}%")
        t3.metric("Total agent latency", f"{result.trace.total_latency_s}s")
    else:
        st.info("Run the pipeline to see the orchestration trace.")
