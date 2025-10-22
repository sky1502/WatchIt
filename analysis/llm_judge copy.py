from __future__ import annotations
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
# from langchain_community.chat_models import ChatOllama
from langchain_ollama import ChatOllama
from langchain.schema import SystemMessage, HumanMessage
from core.config import settings

# Structured output schema
class JudgeOut(BaseModel):
    is_harmful: bool
    categories: List[str] = Field(default_factory=list)
    severity: str        # "low" | "medium" | "high"
    rationale: str       # <= 30 words
    action: str          # "allow" | "warn" | "blur" | "block" | "notify"

SYSTEM_PROMPT = (
"You are a children's online safety classifier running on-device. "
"Evaluate if the given webpage content is suitable for a 10–13 year old. "
"Consider violence, sexual content, profanity, drugs, self-harm, hate. "
"Be conservative. If unsure, choose 'warn'. "
"Output STRICT JSON with keys: is_harmful (bool), categories (array), "
"severity (low|medium|high), rationale (<=30 words), action (allow|warn|blur|block|notify)."
)

def build_human_prompt(page_title: str, domain: str, fast_scores: Dict[str, float], text_sample: str) -> str:
    # Keep payload compact (cap text to ~2000 chars)
    text_snippet = (text_sample or "")[:2000]
    return (
        f"PAGE_TITLE: {page_title}\n"
        f"DOMAIN: {domain}\n"
        f"FAST_SCORES: {fast_scores}\n"
        f"TEXT_SNIPPET:\n{text_snippet}\n\n"
        "Return STRICT JSON only."
    )

class LLMJudge:
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model or settings.ollama_model
        # self.client = ChatOllama(
        #   model=self.model, 
        #   base_url=base_url or settings.ollama_base_url, 
        #   temperature=0)
        self.client = ChatOllama(
            model=self.model,
            base_url=base_url or settings.ollama_base_url,
            temperature=0,
        )


    def judge(self, page_title: str, domain: str, fast_scores: Dict[str, float], text_sample: str) -> Dict[str, Any]:
        prompt = build_human_prompt(page_title, domain, fast_scores, text_sample)
        msgs = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        resp = self.client.invoke(msgs)
        raw = resp.content.strip()
        # strict JSON expected; handle minor formatting issues defensively
        import json
        try:
            data = json.loads(raw)
        except Exception:
            # fallback: attempt to extract JSON block
            import re
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {
                "is_harmful": False, "categories": [], "severity":"low",
                "rationale":"fallback allow", "action":"allow"
            }
        # Validate via Pydantic (enforces fields/types)
        return JudgeOut(**data).model_dump()
