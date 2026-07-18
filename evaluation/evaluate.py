"""
Evaluation harness (Objective 6: Testing & Evaluation).

Runs the full multi-agent pipeline on a fixed sample set and reports:

  RELIABILITY  - agent success rate, whether every stage produced output,
                 how many sources failed retrieval.
  ACCURACY     - keyword-coverage of the report vs. the source material
                 (a lightweight, reference-free faithfulness proxy) and whether
                 expected ground-truth terms appear.
  EFFICIENCY   - total wall-clock time, per-agent latency, and the wall-clock
                 speed-up from running summarization in parallel vs. serial.

Usage:
    python evaluation/evaluate.py            # offline (no key needed)
    LLM_PROVIDER=groq GROQ_API_KEY=... python evaluation/evaluate.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from utils.extractive import keywords  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "sample_data")

# terms we expect a faithful report to surface from the sample corpus
GROUND_TRUTH_TERMS = ["mena", "cloud", "revenue", "churn", "devops", "sre"]


def _load_sources():
    sources = []
    pdf = os.path.join(SAMPLE, "sample_market_memo.pdf")
    csv = os.path.join(SAMPLE, "sample_sales.csv")
    if os.path.exists(pdf):
        with open(pdf, "rb") as f:
            sources.append({"kind": "pdf", "bytes": f.read(), "title": "sample_market_memo.pdf"})
    if os.path.exists(csv):
        with open(csv, "rb") as f:
            sources.append({"kind": "csv", "bytes": f.read(), "title": "sample_sales.csv"})
    sources.append({
        "kind": "text",
        "title": "analyst_note",
        "text": "DevOps and SRE hiring in Egypt accelerated in 2026 with strong Jenkins and Kubernetes demand.",
    })
    return sources


def _keyword_coverage(report_md: str, source_text: str, top_n: int = 15) -> float:
    src_kw = set(keywords(source_text, top_n=top_n))
    if not src_kw:
        return 0.0
    report_l = report_md.lower()
    hit = sum(1 for k in src_kw if k in report_l)
    return round(hit / len(src_kw), 3)


def _ground_truth_recall(report_md: str) -> float:
    report_l = report_md.lower()
    hit = sum(1 for t in GROUND_TRUTH_TERMS if t in report_l)
    return round(hit / len(GROUND_TRUTH_TERMS), 3)


def run_once(parallel_workers: int):
    s = Settings()
    s.parallel_workers = parallel_workers
    orch = Orchestrator(s)
    t0 = time.time()
    res = orch.run(
        _load_sources(),
        report_title="Evaluation Run",
        objective="Assess MENA cloud growth and talent gaps",
    )
    wall = time.time() - t0
    return res, wall


def main():
    print("=" * 68)
    print(" MULTI-AGENT SYSTEM - EVALUATION REPORT")
    print("=" * 68)

    res, wall_parallel = run_once(parallel_workers=4)

    # source text for accuracy proxies
    source_text = " ".join(d.text for d in res.documents)
    report_md = res.report.get("markdown", "")

    # ---- RELIABILITY ----
    n_expected_sources = 3
    reliability = {
        "sources_retrieved": len(res.documents),
        "sources_expected": n_expected_sources,
        "retrieval_completeness": round(len(res.documents) / n_expected_sources, 3),
        "agent_success_rate": res.trace.success_rate(),
        "report_produced": bool(report_md),
        "email_produced": bool(res.email.get("subject")),
        "dashboard_produced": bool(res.dashboard.get("metrics")),
        "pdf_produced": bool(res.report.get("pdf_bytes")),
    }

    # ---- ACCURACY ----
    accuracy = {
        "keyword_coverage": _keyword_coverage(report_md, source_text),
        "ground_truth_recall": _ground_truth_recall(report_md),
        "analysis_engine": res.analysis.get("_engine", "n/a"),
        "sentiment": res.analysis.get("overall_sentiment", "n/a"),
    }

    # ---- EFFICIENCY (parallel vs serial) ----
    res_serial, wall_serial = run_once(parallel_workers=1)
    speedup = round(wall_serial / wall_parallel, 2) if wall_parallel else 0.0
    efficiency = {
        "wall_clock_parallel_s": round(wall_parallel, 3),
        "wall_clock_serial_s": round(wall_serial, 3),
        "parallel_speedup_x": speedup,
        "total_agent_latency_s": res.trace.total_latency_s,
        "per_agent_latency_s": {
            k: v for k, v in sorted(
                {e.agent: 0 for e in res.trace.events}.items()
            )
        },
    }
    # fill per-agent latency
    per_agent = {}
    for e in res.trace.events:
        per_agent[e.agent] = round(per_agent.get(e.agent, 0.0) + e.latency_s, 3)
    efficiency["per_agent_latency_s"] = per_agent

    def _section(name, d):
        print(f"\n[{name}]")
        for k, v in d.items():
            print(f"  {k:.<32} {v}")

    _section("RELIABILITY", reliability)
    _section("ACCURACY", accuracy)
    _section("EFFICIENCY", efficiency)
    if speedup < 1.0:
        print("  note: parallel < serial here because extractive summarization is")
        print("        near-instant offline, so thread overhead dominates. With a")
        print("        real LLM (each call ~1-3s) parallel summarization wins clearly.")

    # ---- pass/fail gates ----
    print("\n[GATES]")
    gates = {
        "all sources retrieved": reliability["retrieval_completeness"] == 1.0,
        "agent success >= 0.9": reliability["agent_success_rate"] >= 0.9,
        "all outputs produced": all(
            [reliability["report_produced"], reliability["email_produced"],
             reliability["dashboard_produced"]]
        ),
        "ground-truth recall >= 0.5": accuracy["ground_truth_recall"] >= 0.5,
    }
    for name, ok in gates.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    overall = all(gates.values())
    print("\n" + "=" * 68)
    print(f" OVERALL: {'PASS' if overall else 'FAIL'}")
    print("=" * 68)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
