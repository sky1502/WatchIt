from __future__ import annotations
import asyncio
from typing import Dict, Any
from core.db import db
from core.config import settings
from core.activity_logger import log_step
from analysis.graph import app_graph, MonitorState
from policy.engine import PolicyEngine

class DecisionBus:
    def __init__(self):
        self._subs = set()

    def subscribe(self):
        q = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q):
        self._subs.discard(q)

    async def publish(self, message: Dict[str, Any]):
        for q in list(self._subs):
            await q.put(message)

bus = DecisionBus()
policy = PolicyEngine()

async def process_event(event: Dict[str, Any], *, upgrade: bool = False) -> Dict[str, Any]:
    event_id = event.get("id")
    if not upgrade or not event_id:
        event_id = db.add_event(event)
        event["id"] = event_id
    else:
        db.update_event_data_json(event_id, event.get("data_json") or "")

    child_id = event.get("child_id")
    profile = db.get_child_profile(child_id) if child_id else None
    if not profile and child_id:
        db.add_child_profile(child_id)
        profile = db.get_child_profile(child_id)
    if not profile:
        profile = {"id": child_id or "child_default", "strictness": "standard", "age": 12}

    log_step("event_received", event, {"upgrade": upgrade})
    state = MonitorState(event=event, child_profile=profile)
    state = MonitorState(**app_graph.invoke(state))

    db.add_analysis(event_id, "fast+ocr", "1.0", state.fast_scores, label="")
    if state.judge_json:
        db.add_analysis(event_id, "llm_judge", "1.0", state.judge_json, label=state.judge_json.get("action",""))
    if state.headline_result:
        db.add_analysis(event_id, "headline_agent", "1.0", state.headline_result, label=state.headline_result.get("risk",""))

    confidence = state.judge_json.get("confidence", 1.0) if state.judge_json else 1.0
    need_screenshot = settings.enable_ocr and not upgrade and state.needs_screenshot

    decision = policy.decide(event, state.fast_scores, state.judge_json, profile, state.headline_result)
    db.add_decision(event_id, settings.policy_version, decision["action"], decision["reason"], {"categories": decision.get("categories",[])})

    message = {
        "event_id": event_id,
        **decision,
        "upgrade": bool(upgrade),
        "needs_ocr": need_screenshot,
        "confidence": confidence,
        "url": event.get("url"),
        "title": event.get("title"),
        "headline_agent": state.headline_result,
    }
    log_step("decision_finalized", event, {"decision": decision, "confidence": confidence, "headline_agent": state.headline_result})
    await bus.publish(message)
    return message
