from __future__ import annotations
import asyncio, time, json
from typing import Dict, Any, Callable, Awaitable
from core.db import db
from analysis.graph import app_graph, MonitorState
from policy.engine import PolicyEngine

policy = PolicyEngine()

class DecisionBus:
    """Naive pub-sub bus; API SSE will subscribe here."""
    def __init__(self):
        self._subs = set()  # set of asyncio.Queue

    def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q):
        self._subs.discard(q)

    async def publish(self, message: Dict[str, Any]):
        for q in list(self._subs):
            await q.put(message)

bus = DecisionBus()

async def process_event(event: Dict[str, Any]) -> Dict[str, Any]:
    # persist event
    event_id = db.add_event(event)
    event["id"] = event_id

    # run agentic graph
    state = MonitorState(event=event)
    result = app_graph.invoke(state)
    state = MonitorState(**result)

    # persist analysis
    db.add_analysis(event_id, "fast_keywords", "1.0", state.fast_scores, label="")
    if state.judge_json:
        db.add_analysis(event_id, "llm_judge", "1.0", state.judge_json, label=state.judge_json.get("action",""))

    # policy
    decision = policy.decide(event, state.fast_scores, state.judge_json)
    db.add_decision(event_id, policy.policy_version, decision["action"], decision["reason"],
                    {"categories": decision.get("categories",[])})
    # notify
    message = {"event_id": event_id, **decision}
    await bus.publish(message)
    return message
