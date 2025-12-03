from __future__ import annotations

from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

from analysis.agents import (
    URLMetadataAgent,
    HeadlinesAgent,
    OCRAgent,
    ScreenshotsAgent,
)
from core.config import settings
from core.activity_logger import log_step

HEADLINE_DECISION_THRESHOLD = 0.85


class MonitorState(BaseModel):
    event: Dict[str, Any]
    child_profile: Dict[str, Any] = Field(default_factory=dict)
    fast_scores: Dict[str, float] = Field(default_factory=dict)
    judge_json: Dict[str, Any] = Field(default_factory=dict)
    headline_result: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    ocr_text: str = ""
    need_llm: bool = True
    need_ocr: bool = False
    needs_screenshot: bool = False


headlines_agent = HeadlinesAgent()
url_agent = URLMetadataAgent()
ocr_agent = OCRAgent()
screens_agent = ScreenshotsAgent()


def node_headline_layer(state: MonitorState) -> MonitorState:
    result = headlines_agent.run(state.event, state.child_profile)
    state.fast_scores = result.fast_scores
    state.headline_result = {
        "risk": result.risk,
        "flags": result.flags,
        "confidence": result.confidence,
        "action": result.action,
    }
    state.need_llm = True
    if result.action in ("allow", "block") and result.confidence >= HEADLINE_DECISION_THRESHOLD:
        # Early exit: treat headline decision as authoritative
        state.need_llm = False
        state.judge_json = {
            "action": result.action,
            "categories": result.flags,
            "severity": "medium" if result.action == "block" else "low",
            "rationale": "headline_agent_decision",
            "confidence": result.confidence,
            "is_harmful": result.action != "allow",
        }
        state.confidence = result.confidence
    log_step(
        "headline_layer",
        state.event,
        {
            "action": state.headline_result["action"],
            "risk": state.headline_result["risk"],
            "confidence": state.headline_result["confidence"],
            "flags": state.headline_result["flags"],
        },
    )
    return state


def node_url_layer(state: MonitorState) -> MonitorState:
    if not state.need_llm:
        return state
    result = url_agent.run(
        state.event,
        state.child_profile,
        extra_text=state.ocr_text,
        fast_scores=state.fast_scores or None,
    )
    state.fast_scores = result.fast_scores
    state.judge_json = result.llm_decision
    state.confidence = result.confidence
    # Treat any low-confidence or non-allow verdict as uncertain and trigger OCR.
    llm_action = (result.llm_decision or {}).get("action", "").lower()
    llm_severity = (result.llm_decision or {}).get("severity", "").lower()
    uncertain = (
        result.confidence < settings.ocr_confidence_threshold
        or llm_action in {"warn", "blur", "notify"}
        or llm_severity in {"medium", "high"}
    )
    state.need_ocr = uncertain
    log_step(
        "url_metadata_layer",
        state.event,
        {"llm_decision": result.llm_decision, "confidence": result.confidence},
    )
    return state


def node_ocr_layer(state: MonitorState) -> MonitorState:
    state.needs_screenshot = False
    if not state.need_llm or not state.need_ocr:
        return state

    screenshots = screens_agent.get_screenshots(state.event)
    if not screenshots:
        state.needs_screenshot = True
        log_step(
            "ocr_layer_request_screenshot",
            state.event,
            {
                "reason": "no_screenshots_present",
                "note": "llm_uncertain_no_screenshot_yet",
            },
        )
        return state

    ocr_text = ocr_agent.extract_text(screenshots)
    if not ocr_text:
        log_step(
            "ocr_layer_no_text",
            state.event,
            {
                "reason": "ocr_empty",
                "note": "screenshots_received_but_no_text_detected",
                "screenshot_count": len(screenshots),
            },
        )
        return state

    state.ocr_text = ocr_text
    refreshed = url_agent.run(
        state.event,
        state.child_profile,
        extra_text=ocr_text,
        fast_scores=state.fast_scores or None,
    )
    state.fast_scores = refreshed.fast_scores
    state.judge_json = refreshed.llm_decision
    state.confidence = refreshed.confidence
    state.need_ocr = False
    log_step(
        "ocr_layer",
        state.event,
        {
            "ocr_text_preview": ocr_text[:200],
            "ocr_text_full": ocr_text[:2000],  # log capped full text for debugging
            "llm_decision": refreshed.llm_decision,
            "confidence": refreshed.confidence,
        },
    )
    return state


graph = StateGraph(MonitorState)
graph.add_node("headline_layer", node_headline_layer)
graph.add_node("url_layer", node_url_layer)
graph.add_node("ocr_layer", node_ocr_layer)
graph.add_edge(START, "headline_layer")
graph.add_edge("headline_layer", "url_layer")
graph.add_edge("url_layer", "ocr_layer")
graph.add_edge("ocr_layer", END)
app_graph = graph.compile()
