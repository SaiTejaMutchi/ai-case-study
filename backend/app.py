import logging
import re
from dotenv import load_dotenv
from typing import Optional, Dict, List, Tuple
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# Utils imports
# ============================================================
from utils.part_service import CatalogService
from utils.guardrails import (
    is_in_scope, extract_entities, intent_classify,
    generate_clarifier, Memory, set_extra_scope_keywords
)
from utils.llm_gemini import LLMService
from utils.rag_service import RAGService

# ============================================================
# Logging setup
# ============================================================
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
)
log = logging.getLogger("backend")

log.info("🚀 Bootstrapping FastAPI backend...")
app = FastAPI(title="AI Appliance Assistant", version="2.4")

# ============================================================
# CORS setup
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Initialize Core Services
# ============================================================
log.info("[INIT 1/4] Loading CatalogService...")
try:
    catalog = CatalogService()  # provides catalog.catalog (your Catalog class)
    num_items = len(catalog.catalog.db.get("items", []))
    log.info(f"✅ CatalogService ready with {num_items} items.")
except Exception as e:
    log.exception(f"❌ Failed to load CatalogService: {e}")
    raise

log.info("[INIT 2/4] Loading RAGService...")
try:
    rag = RAGService()
    log.info(f"✅ RAGService initialized with {rag.size()} knowledge chunks.")
except Exception as e:
    log.warning(f"⚠️ RAGService initialization issue: {e}")
    rag = RAGService()

log.info("[INIT 3/4] Initializing Memory...")
memory = Memory()
chat_memory: Dict[str, List[Dict[str, str]]] = {}
log.info("✅ Memory system ready.")

log.info("[INIT 4/4] Initializing LLMService...")
try:
    llm = LLMService()
    log.info("✅ LLMService (Gemini) initialized successfully.")
except Exception as e:
    log.warning(f"⚠️ LLMService unavailable: {e}")
    llm = None

# Extend scope with catalog-driven keywords
try:
    extra_keywords = {
        str(i.get("partNumber", "")).lower()
        for i in catalog.catalog.db.get("items", [])
        if i.get("partNumber")
    } | {
        str(i.get("name", "")).lower()
        for i in catalog.catalog.db.get("items", [])
        if i.get("name")
    }
    set_extra_scope_keywords(extra_keywords)
    log.info(f"🔎 Added {len(extra_keywords)} catalog-based scope keywords.")
except Exception as e:
    log.warning(f"⚠️ Could not extend scope keywords: {e}")

log.info("✅ All core services loaded.\n")

# ============================================================
# Schemas
# ============================================================
class ChatIn(BaseModel):
    message: str
    part: Optional[str] = None
    model: Optional[str] = None
    appliance: str = "dishwasher"  # current front-end context


class ChatOut(BaseModel):
    response: str
    intent: str
    memory: Dict[str, Optional[str]]

# ============================================================
# Helpers
# ============================================================
def never_empty(text: Optional[str]) -> str:
    if not text:
        return "(LLM returned no content.)"
    t = text.strip()
    if not t or t.lower() in {"none", "null", "nan"}:
        return "(LLM returned no content.)"
    return t

def _other_appliance_hint(q: str, current: str) -> Optional[str]:
    s = q.lower()
    if any(k in s for k in ["fridge", "refrigerator", "freezer"]):
        return "refrigerator" if current != "refrigerator" else None
    if any(k in s for k in ["dishwasher", "dish washer"]):
        return "dishwasher" if current != "dishwasher" else None
    return None

def _format_part_list(parts: List[Dict[str, str]]) -> str:
    lines = []
    for p in parts[:5]:
        pn = p.get("partNumber", "Unknown")
        nm = p.get("name", "Unnamed")
        ap = (p.get("appliance") or "").capitalize()
        br = p.get("brand", "")
        lines.append(f"• {pn} – {nm} ({ap}, {br})")
    return "\n".join(lines)

# ============================================================
# Health & Debug
# ============================================================
@app.get("/")
def root():
    return {"status": "ok", "message": "Backend is alive"}

@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "catalog_items": len(catalog.catalog.db.get("items", [])),
        "rag_chunks": rag.size(),
        "llm_ready": bool(llm),
    }

@app.get("/debug/lookup")
def debug_lookup(q: str):
    hits = catalog.catalog.search(q)
    return {"q": q, "hits": hits[:10], "count": len(hits)}

# ============================================================
# Main Chat Endpoint
# ============================================================
@app.post("/chat", response_model=ChatOut)
async def chat(inp: ChatIn, x_session_id: Optional[str] = Header(default="demo")):
    log.info(f"\n=== 🧠 New Chat Session [{x_session_id}] ===")
    q = (inp.message or "").strip()
    cur_appliance = (inp.appliance or "dishwasher").lower()
    log.info(f"User Query: {q}")
    log.info(f"Appliance Context: {cur_appliance}")

    # Build/trim session chat history
    if x_session_id not in chat_memory:
        chat_memory[x_session_id] = []
    session_chat_history = chat_memory[x_session_id]
    session_chat_history.append({"role": "user", "content": q})
    if len(session_chat_history) > 8:
        chat_memory[x_session_id] = session_chat_history[-8:]

    # ===== 0) Special control message from frontend: refusal marker =====
    if "user refused switch" in q.lower():
        # Remember the last time user refused; store which appliance they refused switching TO
        memory.update(x_session_id, last_switch_refused_for=cur_appliance)
        return ChatOut(
            response=f"Got it — staying with your current {cur_appliance} context.",
            intent="ack_refuse",
            memory=memory.get(x_session_id),
        )

    # ============================================================
    # [1] Get Memory (Moved Up)
    # We need memory right away to check for switch refusals
    # ============================================================
    mem = memory.get(x_session_id)

    # ============================================================
    # [2] Appliance Mismatch Guard (NEW)
    # Check for explicit appliance keywords *before* scope/intent checks.
    # ============================================================
    alt_appliance = _other_appliance_hint(q, cur_appliance)
    refused_for = (mem or {}).get("last_switch_refused_for")

    if alt_appliance and refused_for != alt_appliance:
        # User is asking about another appliance and hasn't refused yet.
        log.info(f"🧭 Cross-appliance query detected ('{alt_appliance}') → suggest switch.")
        return ChatOut(
            response=(
                f"It sounds like you’re asking about a <strong>{alt_appliance}</strong>. "
                f"You can say “switch to {alt_appliance}” or click the switch button to change context."
            ),
            intent="switch_suggestion",
            memory=mem,
        )
    elif alt_appliance and refused_for == alt_appliance:
        # User is *still* asking about it, but we respect their refusal
        log.info("🧩 User previously refused switching; proceeding in current context without suggesting again.")

    # ============================================================
    # [3] Soft Scope Guard (Was [1], and simplified)
    # ============================================================
    if not is_in_scope(q, appliance_context=cur_appliance):
        # We already handled the alt_appliance case,
        # so now we just log if it's out of scope *without* an appliance hint.
        log.info("💡 Question outside current context but continuing gracefully.")

    # ============================================================
    # [4] Entity Extraction (Was [2])
    # ============================================================
    ent = extract_entities(q)
    if inp.part:
        ent.setdefault("part", inp.part)
    if inp.model:
        ent.setdefault("model", inp.model)
    # mem = memory.get(x_session_id) <-- This line is no longer needed here
    ent["part"] = ent.get("part") or mem.get("last_part")
    ent["model"] = ent.get("model") or mem.get("last_model")
    log.info(f"🔍 Extracted entities: {ent}")

    # ============================================================
    # [5] Intent Classification (Was [3])
    # ============================================================
    intent = intent_classify(q)
    itype = intent.get("type") if isinstance(intent, dict) else str(intent)
    conf = float(intent.get("confidence", 1.0)) if isinstance(intent, dict) else 1.0
    log.info(f"🎯 Intent classified as '{itype}' (confidence={conf:.2f})")

    # ============================================================
    # [6] Part Search (intelligent + cross-appliance aware) (Was [4])
    # ============================================================
    part_search_keywords = [
        "show me", "find", "replacement", "rack", "pump", "valve", "filter",
        "tray", "basket", "drawer", "bin", "door", "crisper", "shelf", "track", "roller", "adjuster"
    ]
    if any(k in q.lower() for k in part_search_keywords):
        itype = "part_search"
        try:
            # Brand/category hints
            brand_match = re.search(
                r"\b(whirlpool|maytag|ge|frigidaire|samsung|lg|bosch|kitchenaid|amana|kenmore)\b",
                q, re.I
            )
            brand = brand_match.group(1) if brand_match else None

            category_keywords = [
                "rack", "pump", "filter", "hose", "tray", "door", "handle",
                "drawer", "basket", "bin", "valve", "crisper", "shelf", "track", "roller", "adjuster"
            ]
            category = next((w for w in category_keywords if w in q.lower()), None)

            # Detect other appliance and check refusal memory
            # Note: We already did this check above for the 'switch_suggestion'.
            # We re-check 'other' and 'refused_for' here *only* to decide
            # which appliance_hint to pass to catalog.find_parts.
            other = _other_appliance_hint(q, cur_appliance)
            refused_for = (mem or {}).get("last_switch_refused_for")

            # This logic is now simplified:
            # If user mentioned 'other' and refused, search for 'other' in 'current' context.
            # Otherwise, just use the 'current' context.
            appliance_hint = other if (other and refused_for == other) else cur_appliance

            results = catalog.catalog.find_parts(
                appliance_type=appliance_hint,
                brand=brand,
                category=category,
                query=q
            )

            switch_note = ""
            if other and refused_for == other:
                switch_note = (
                    f"\n\n(You mentioned <strong>{other}</strong> but chose to stay. "
                    f"You can switch anytime with the floating toggle.)"
                )
            
            # Format response
            if results and results[0].get("partNumber") != "N/A":
                list_str = _format_part_list(results)
                return ChatOut(
                    response=(
                        f"Here are some {category or 'relevant'} parts I found for "
                        f"{(brand or appliance_hint.title())}:{switch_note}\n{list_str}"
                    ),
                    intent="part_search",
                    memory=memory.get(x_session_id),
                )

            # Fallback to official URL if no local matches
            fallback_url = results[0].get("officialURL") if results else None
            link = f"\nTry the official catalog: {fallback_url}" if fallback_url else ""
            return ChatOut(
                response=(
                    f"I couldn’t find specific {category or 'replacement'} parts locally "
                    f"for {brand or 'this brand'} {cur_appliance}.{switch_note}{link}"
                ),
                intent="part_search",
                memory=memory.get(x_session_id),
            )

        except Exception as e:
            log.warning(f"⚠️ Smart part search error: {e}")

    # ============================================================
    # [7] Installation (Was [5])
    # ============================================================
    if itype == "installation":
        part_num = ent.get("part")
        guide = catalog.catalog.install_guide(part_num)
        memory.update(x_session_id, last_part=part_num, last_intent="installation")
        return ChatOut(response=guide, intent="installation", memory=memory.get(x_session_id))

    # ============================================================
    # [8] Compatibility (Was [6])
    # ============================================================
    if itype == "compatibility":
        part_num = ent.get("part") or (mem or {}).get("last_part")
        model_hint = ent.get("model") or (mem or {}).get("last_model")
        if part_num and model_hint:
            ok, message = catalog.catalog.is_compatible(part_num, model_hint)
            memory.update(x_session_id, last_part=part_num, last_model=model_hint, last_intent="compatibility")
            return ChatOut(response=message, intent="compatibility", memory=memory.get(x_session_id))

    # ============================================================
    # [9] Fallback: RAG (Was [7])
    # ============================================================
    log.info(f"Falling back to RAG for intent: {itype}")
    docs = rag.search(q, appliance_context=cur_appliance, k=6)
    prompt = rag.build_prompt(q, docs, session_chat_history, cur_appliance)

    reply = never_empty(await llm.answer(prompt)) if llm else "LLM unavailable."
    chat_memory[x_session_id].append({"role": "assistant", "content": reply})
    memory.update(x_session_id, last_intent=itype)

    return ChatOut(response=reply, intent=itype, memory=memory.get(x_session_id))