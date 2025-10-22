from __future__ import annotations
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field
from analysis.safety import SafetyAnalyzer
from analysis.llm_judge import LLMJudge
import json
from urllib.parse import urlparse

class MonitorState(BaseModel):
    event: Dict[str, Any]
    fast_scores: Dict[str, float] = Field(default_factory=dict)
    judge_json: Dict[str, Any] = Field(default_factory=dict)

analyzer = SafetyAnalyzer()
judge = LLMJudge()

def node_fast_scores(state: MonitorState) -> MonitorState:
    scores = analyzer.analyze_event_fast(state.event)
    state.fast_scores = scores
    return state

def node_llm_judge(state: MonitorState) -> MonitorState:
    e = state.event
    data = {}
    if e.get("data_json"):
        try: data = json.loads(e["data_json"])
        except Exception: data = {}
    text = data.get("dom_sample") or data.get("text") or ""
    title = e.get("title") or ""
    domain = (urlparse(e.get("url") or "").netloc or "").lower()
    out = judge.judge(title, domain, state.fast_scores, text)
    state.judge_json = out
    return state

# Graph: START -> fast_scores -> llm_judge -> END
graph = StateGraph(MonitorState)
graph.add_node("fast_scores", node_fast_scores)
graph.add_node("llm_judge", node_llm_judge)
graph.add_edge(START, "fast_scores")
graph.add_edge("fast_scores", "llm_judge")
graph.add_edge("llm_judge", END)
app_graph = graph.compile()
