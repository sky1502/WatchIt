from __future__ import annotations
from runtime.bootstrap import MonitorState
from fastapi import FastAPI, HTTPException, Depends, Body
from pydantic import BaseModel
from core.config import settings
from core.db import db

import asyncio
from fastapi.responses import StreamingResponse
from app.api_models import EventInput
from runtime.bootstrap import process_event, bus

import traceback, logging
logger = logging.getLogger("watchit.api")

app = FastAPI(title="WatchIt Local API", version="0.1.0",
              description="Local-only parental monitoring with Ollama LLM judge")

class PinPayload(BaseModel):
    pin: str

class PausePayload(BaseModel):
    pin: str
    minutes: int = 15

@app.post("/v1/control/pause")
async def control_pause(body: PausePayload):
    if body.pin != settings.parent_pin:
        raise HTTPException(403, "Invalid PIN")
    until_ms = int(__import__("time").time()*1000 + body.minutes*60*1000)
    cur = db.conn.cursor()
    cur.execute("INSERT INTO settings(key,value) VALUES('paused_until', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(until_ms),))
    db.conn.commit()
    return {"ok": True, "paused_until": until_ms}

@app.post("/v1/control/resume")
async def control_resume(body: PinPayload):
    if body.pin != settings.parent_pin:
        raise HTTPException(403, "Invalid PIN")
    cur = db.conn.cursor()
    cur.execute("DELETE FROM settings WHERE key='paused_until'")
    db.conn.commit()
    return {"ok": True}

@app.post("/v1/event")
async def post_event(evt: EventInput):
    try:
        event_dict = evt.model_dump()         # ✅ convert Pydantic -> dict
        decision = await process_event(event_dict)
        return decision
    except Exception as e:
        logger.error("Error in /v1/event: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, str(e))

@app.get("/v1/events")
async def get_events(child_id: str | None = None, limit: int = 50):

    return {"events": db.get_recent_events(child_id, limit)}

@app.get("/v1/decisions")
async def get_decisions(child_id: str | None = None, limit: int = 50):
    return {"decisions": db.get_recent_decisions(child_id, limit)}

@app.get("/v1/stream/decisions")
async def stream_decisions():
    from app.sse import sse_generator
    q = bus.subscribe()
    async def _cleanup():
        bus.unsubscribe(q)
    return StreamingResponse(sse_generator(q), media_type="text/event-stream", background=None)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        reload=True,
    )