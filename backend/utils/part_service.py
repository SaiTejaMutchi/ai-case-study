import logging
from typing import List, Dict, Optional, Tuple
from utils.catalog_class import Catalog

log = logging.getLogger("backend")
import logging
from typing import List, Dict, Optional, Tuple
from utils.catalog_class import Catalog

log = logging.getLogger("backend")

def _norm(code: Optional[str]) -> Optional[str]:
    if not code: return None
    return code.strip().upper()

class CatalogService:
    def __init__(self, path: str = "data/parts_catalog.json"):
        self.catalog = Catalog(path)
        log.info(f"✅ CatalogService initialized with {len(self.catalog.db.get('items', []))} items.")

    # ============================================================
    # 🔍 Simple keyword-based part finder
    # ============================================================
    def find_parts(self, appliance_type=None, brand=None, category=None):
        """
        Lightweight keyword search across the local parts catalog.
        Matches appliance type + category (like 'rack', 'filter', 'door gasket').
        """
        items = self.catalog.db.get("items", [])
        if not items:
            return []

        results = []
        cat_term = (category or "").lower()
        brand_term = (brand or "").lower() if brand else ""

        for item in items:
            name = str(item.get("name", "")).lower()
            desc = str(item.get("description", "")).lower()
            appl = str(item.get("applianceType", "")).lower()
            brand_name = str(item.get("brand", "")).lower()

            # Match conditions
            if appliance_type and appliance_type not in appl:
                continue
            if brand_term and brand_term not in brand_name:
                continue
            if cat_term and cat_term not in name and cat_term not in desc:
                continue

            results.append(item)

        # Sort by how many times the keyword appears
        results.sort(key=lambda p: str(p.get("name", "")).lower().count(cat_term), reverse=True)
        return results[:10]  # return top 10 matches


    # UI feature
    def get_featured_parts(self) -> List[Dict]:
        return self.catalog.featured()

    # Core
    def search_parts(self, query: str, part: Optional[str] = None, model: Optional[str] = None) -> List[Dict]:
        return self.catalog.search(query, part, model)

    def get_install_guide(self, part: Optional[str], model: Optional[str] = None) -> str:
        guide = self.catalog.install_guide(part, model)
        return guide or "No specific guide available. Refer to general replacement steps."

    def find_parts_by_symptom(self, issue: str, model: Optional[str] = None) -> Dict[str, any]:
        text = self.catalog.troubleshoot(issue, model)
        return {"guidance": text, "parts": []}

    def check_compatibility(self, part: str, model: str) -> Tuple[bool, str]:
        return self.catalog.is_compatible(part, model)

    # Helpers
    def get_part_by_number(self, code: str) -> Optional[Dict]:
        """Try multiple keys: partNumber, manufacturerPart, aliases."""
        codeN = _norm(code)
        if not codeN: return None
        items = self.catalog.db.get("items", [])
        for p in items:
            if _norm(p.get("partNumber")) == codeN:
                return p
            if _norm(p.get("manufacturerPart")) == codeN:
                return p
            # optional aliases list in catalog
            for a in (p.get("aliases") or []):
                if _norm(a) == codeN:
                    return p
        # fallback: substring search across common fields
        for p in items:
            hay = " ".join(str(p.get(k,"")) for k in ("partNumber","manufacturerPart","name")).upper()
            if codeN in hay:
                return p
        return None
