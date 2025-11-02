import re
import logging
from typing import Set, Dict, Optional, List

log = logging.getLogger("backend")

# --- In-Scope Keywords ---

# Core keywords that define the bot's purpose
CORE_KEYWORDS = {
    "part", "parts", "model", "number", "serial", "replacement", "repair",
    "fix", "broken", "install", "installation", "guide", "steps",
    "compatible", "fit", "compatibility", "buy", "order", "find",
    "partselect", "oem",
}

# Appliance-specific keywords
APPLIANCE_KEYWORDS = {
    "appliance", "appliances",
    "dishwasher", "dish", "washer",
    "refrigerator", "fridge", "freezer", "ice", "icemaker",
}

# Common part names
PART_KEYWORDS = {
    "rack", "basket", "wheel", "roller", "gasket", "seal", "pump", "motor",
    "hose", "tube", "inlet", "valve", "filter", "water", "drain", "panel",
    "handle", "latch", "door", "shelf", "bin", "drawer", "crisper", "light",
    "bulb", "heating", "element", "thermostat", "sensor", "board", "control",
}

# Dynamic set for catalog part numbers
EXTRA_CATALOG_KEYWORDS: Set[str] = set()

def set_extra_scope_keywords(keywords: Set[str]):
    """Allow main.py to inject catalog keywords (part numbers, etc.)"""
    global EXTRA_CATALOG_KEYWORDS
    EXTRA_CATALOG_KEYWORDS = keywords
    log.info(f"🔧 Extended in-scope keywords: {len(EXTRA_CATALOG_KEYWORDS)} added.")

# --- FIX: This function now accepts 'appliance_context' ---
def is_in_scope(query: str, appliance_context: str = "appliance") -> bool:
    """
    Checks if the query is related to appliance repair.
    This now uses the appliance_context for a more targeted check.
    """
    q_lower = query.lower()
    
    # 1. Check for explicit out-of-scope topics
    OOS_KEYWORDS = {"car", "auto", "truck", "boat", "computer", "phone", "tv"}
    if any(word in q_lower for word in OOS_KEYWORDS):
        log.warning(f"Query '{q_lower}' flagged as out-of-scope (OOS keyword).")
        return False

    # 2. Check for keywords related to the *current* appliance context
    # This is the most important check.
    context_keywords = {appliance_context, "part", "parts", "model"}
    if appliance_context == "dishwasher":
        context_keywords.update({"dishwasher", "dish", "rack", "pump"})
    elif appliance_context == "refrigerator":
        context_keywords.update({"refrigerator", "fridge", "filter", "ice", "drawer", "bin"})

    if any(word in q_lower for word in context_keywords):
        return True

    # 3. Check for general appliance/part keywords
    all_scope_words = CORE_KEYWORDS | APPLIANCE_KEYWORDS | PART_KEYWORDS | EXTRA_CATALOG_KEYWORDS
    if any(word in q_lower for word in all_scope_words):
        return True

    log.warning(f"Query '{q_lower}' flagged as out-of-scope (No keywords matched).")
    return False

# ============================================================
# Entity Extraction
# ============================================================

# Regex for PartSelect part numbers (e.g., PS11752778)
PART_REGEX = re.compile(r'\b(PS|AP|WP|WR|WD|DA|W10|W11|242|530)\d{6,}\b', re.IGNORECASE)
# Regex for common model numbers
MODEL_REGEX = re.compile(r'\b(\w{3,}\d{3,}\w*)\b')

def extract_entities(query: str) -> Dict[str, Optional[str]]:
    """Extracts part numbers and model numbers from the query."""
    part_match = PART_REGEX.search(query)
    
    # Simple model extraction: find the *longest* alpha-numeric string
    # that isn't a part number.
    model_match = None
    potential_models = MODEL_REGEX.findall(query)
    if potential_models:
        potential_models.sort(key=len, reverse=True)
        for model in potential_models:
            if not part_match or model.upper() != part_match.group(0).upper():
                model_match = model
                break
                
    return {
        "part": part_match.group(0).upper() if part_match else None,
        "model": model_match.upper() if model_match else None
    }

# ============================================================
# Intent Classification (Simple)
# ============================================================

def intent_classify(query: str) -> Dict[str, any]:
    """
    A simple keyword-based intent classifier.
    Returns a dict with 'type' and 'confidence'.
    """
    q = query.lower()

    if "compatible" in q or "fit" in q or "work with" in q:
        return {"type": "compatibility", "confidence": 0.95}
    
    if "how to" in q or "install" in q or "replace" in q or "remove" in q:
        return {"type": "installation", "confidence": 0.9}

    if "leaking" in q or "not cooling" in q or "not draining" in q or "loud noise" in q or "won't start" in q or "ice maker not working" in q:
        return {"type": "symptom", "confidence": 0.9}
        
    if "find" in q or "need" in q or "buy" in q or "part for" in q or "looking for" in q or PART_KEYWORDS.intersection(q.split()):
        return {"type": "part_lookup", "confidence": 0.8}

    return {"type": "general_help", "confidence": 0.7}

# ============================================================
# Clarification Generator
# ============================================================

def generate_clarifier(intent_type: str) -> str:
    """Generates a clarification question if confidence is low."""
    clarifiers = {
        "compatibility": "To check compatibility, I'll need the part number and your appliance's model number. Do you have those?",
        "installation": "It sounds like you're looking for installation steps. Could you tell me the part you're working with?",
        "symptom": "It sounds like you're diagnosing a problem. Can you tell me a bit more about what's happening?",
        "part_lookup": "I can help you find that. What part are you looking for?",
        "general_help": "I'm not quite sure what you mean. Could you rephrase that? You can ask me to find parts, check compatibility, or get repair guides."
    }
    return clarifiers.get(intent_type, clarifiers["general_help"])

# ============================================================
# Memory Service
# ============================================================

class Memory:
    """
    A simple in-memory key-value store for session data.
    In a real app, this would be Redis or a database.
    """
    def __init__(self):
        self._store: Dict[str, Dict[str, Optional[str]]] = {}

    def _get_or_create(self, session_id: str) -> Dict[str, Optional[str]]:
        if session_id not in self._store:
            self._store[session_id] = {
                "last_intent": None,
                "last_part": None,
                "last_model": None,
            }
        return self._store[session_id]

    def get(self, session_id: str) -> Dict[str, Optional[str]]:
        return self._get_or_create(session_id).copy()

    def update(self, session_id: str, **kwargs):
        session = self._get_or_create(session_id)
        for key, value in kwargs.items():
            if key in session:
                session[key] = value
                log.info(f"🧠 Memory [{session_id}]: Set {key} = {value}")

