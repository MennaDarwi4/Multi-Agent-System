"""
QAAgent  (Ask Argus - interactive Q&A over the analyzed sources)

Answers a user's question grounded ONLY in the sources retrieved during the last
run. Uses the Groq LLM when available; otherwise falls back to a dependency-free
extractive retrieval so questions still get a useful, source-backed answer.

Context is a list of {"title": str, "text": str} blocks (the retrieved sources),
passed in by the caller so this agent stays stateless.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from llm_client import LLMError
from utils.extractive import keywords as extract_keywords
from utils.extractive import split_sentences

_SYSTEM = (
    "You are Argus, a market-intelligence analyst. Answer the user's question "
    "using ONLY the provided sources. Cite the sources you use inline as "
    "[Source N]. If the answer is not contained in the sources, say so plainly "
    "instead of guessing. Be concise and concrete."
)


class QAAgent(BaseAgent):
    name = "QAAgent"

    def answer(self, question: str, context: List[Dict[str, str]]) -> Dict[str, Any]:
        t0 = time.time()
        question = (question or "").strip()
        if not question:
            return {"answer": "Please enter a question.", "grounded": False}
        if not context:
            return {
                "answer": "No analyzed sources are available. Run Argus first.",
                "grounded": False,
            }

        if self.llm.available:
            try:
                blocks = "\n\n".join(
                    f"[Source {i}] {c.get('title', 'untitled')}\n{c.get('text', '')}"
                    for i, c in enumerate(context, 1)
                )
                prompt = f"SOURCES:\n{blocks}\n\nQUESTION: {question}"
                res = self.llm.chat(_SYSTEM, prompt)
                self._record("ask", "ok", time.time() - t0,
                             detail=f"LLM {res.model}", model=res.model)
                return {"answer": res.text, "grounded": True, "engine": f"llm:{res.model}"}
            except LLMError as e:
                self._record("ask", "fallback", time.time() - t0, detail=str(e))

        # extractive fallback: rank source sentences by overlap with the question
        answer = self._extractive_answer(question, context)
        self._record("ask", "fallback", time.time() - t0, detail="extractive answer")
        return {"answer": answer, "grounded": True, "engine": "extractive"}

    @staticmethod
    def _extractive_answer(question: str, context: List[Dict[str, str]]) -> str:
        q_kws = set(extract_keywords(question, top_n=8))
        if not q_kws:
            return "Please ask a more specific question about your sources."

        scored = []
        for c in context:
            title = c.get("title", "source")
            for sent in split_sentences(c.get("text", "")):
                overlap = len(q_kws & set(extract_keywords(sent, top_n=12)))
                if overlap:
                    scored.append((overlap, title, sent))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:4]
        if not top:
            return ("I couldn't find that in the analyzed sources. "
                    "Try rephrasing, or add a source that covers it.")
        return "Based on your sources:\n\n" + "\n".join(
            f"- ({title}) {sent}" for _, title, sent in top
        )
