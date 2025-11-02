import json, os, re
from typing import List, Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup

PARTNUM_RE = re.compile(r"\b[A-Z]{1,3}\d{4,8}[A-Z]?\b", re.I)
BRANDS = {"whirlpool","maytag","ge","frigidaire","samsung","lg","bosch","kitchenaid","amana","kenmore"}
APPLIANCES = {"dishwasher","refrigerator","fridge","freezer"}

def _lc(s: Optional[str]) -> str: return (s or "").strip().lower()
def _tokens(s: str) -> List[str]: return re.findall(r"[a-z0-9\-]+", _lc(s))

CATEGORY_KEYS = {
  "rack": {"rack","dishrack","upper","lower","basket","silverware","cutlery","adjuster","roller","track","clip","drawer","tray"},
  "pump": {"pump","drain","wash","circulation"},
  "filter": {"filter"},
  "hose": {"hose","inlet","drain","line"},
  "valve": {"valve","inlet","water"},
  "door": {"door","gasket","seal","latch","hinge"},
  "tray": {"tray","shelf","bin","drawer","crisper"},
  "ice": {"ice","icemaker","ice-maker","auger","bucket"},
}

def _guess_brand(t: str) -> Optional[str]:
    tl = _lc(t)
    for b in BRANDS:
        if b in tl: return b.capitalize()
    return None

def _guess_appliance(t: str, default: Optional[str]=None) -> Optional[str]:
    tl = _lc(t)
    if "dishwasher" in tl or "dish washer" in tl: return "dishwasher"
    if any(k in tl for k in ["refrigerator","fridge","freezer"]): return "refrigerator"
    return default

def _guess_category(t: str) -> Optional[str]:
    tl = _lc(t)
    best, hits = None, 0
    for cat, keys in CATEGORY_KEYS.items():
        k = sum(1 for kw in keys if kw in tl)
        if k > hits: best, hits = cat, k
    return best

class Catalog:
    """
    Parses both Dishwasher + Refrigerator HTML snapshots into a local JSON catalog
    and provides search/compatibility/installation helpers with safe fallbacks.
    """
    def __init__(self, path: str):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(base_dir, "../../"))
        self.json_path = os.path.join(root_dir, path)
        self.html_sources = [
            ("dishwasher",   os.path.join(root_dir, "frontend/public/Official Dishwasher Parts _ Order Today, Ships Today _ PartSelect.html")),
            ("refrigerator", os.path.join(root_dir, "frontend/public/Official Refrigerator Parts _ Order Today, Ships Today _ PartSelect.html")),
        ]
        self.db: Dict[str, Any] = {"items": []}

        self._load_or_build()
        self._build_indices()

    def _load_or_build(self):
        if not os.path.exists(self.json_path):
            self._rebuild_from_html()
        else:
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except Exception:
                self.db = {"items": []}
            if not self.db.get("items"):
                self._rebuild_from_html()

    def _rebuild_from_html(self):
        items: List[Dict[str, Any]] = []
        for appliance, html_path in self.html_sources:
            if not os.path.exists(html_path):
                print(f"⚠️ Missing HTML: {html_path}")
                continue
            items.extend(self._parse_html_to_items(html_path, appliance))
        self.db = {"items": items}
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2)
        print(f"✅ Catalog built with {len(items)} parts")

    def _parse_html_to_items(self, html_path: str, appliance: str) -> List[Dict[str, Any]]:
        with open(html_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        page_brand = _guess_brand(soup.get_text(" ", strip=True)) or "Generic"
        blocks = soup.select(".partlist-item, .ps-part, .product, li")
        out: List[Dict[str, Any]] = []

        for b in blocks:
            text = b.get_text(" ", strip=True)
            if not text: continue

            # part number
            pn = ""
            tpn = b.select_one(".part-number, .ps-part-number, .sku")
            if tpn: pn = tpn.get_text(strip=True)
            if not pn:
                m = PARTNUM_RE.search(text)
                if m: pn = m.group(0).upper()

            # name
            name = ""
            tn = b.select_one(".part-title, .part-name, .title, h3, h4, a")
            if tn: name = tn.get_text(strip=True)
            if not name:
                name = " ".join(text.split()[:10])

            if not pn and not name: continue

            # desc
            desc = ""
            td = b.select_one(".part-description, .ps-part-desc, .desc")
            if td: desc = td.get_text(strip=True)

            # category
            cat = _guess_category(name) or _guess_category(desc) or "general"

            # brand/appliance
            brand = _guess_brand(text) or page_brand
            appl = _guess_appliance(name + " " + desc, appliance)

            # official link (safe fallback)
            official = f"https://www.partselect.com/Search.aspx?SearchTerm={(pn or name).replace(' ', '+')}"

            out.append({
                "partNumber": pn or "",
                "name": name or (pn or "Unknown Part"),
                "brand": brand,
                "appliance": appl or appliance,
                "category": cat,
                "description": desc,
                "officialURL": official,
                "installGuide": None,
                "models": [],       # list pages usually don’t include model tables
                "brands": [brand],
            })

        # dedupe by (pn,name)
        seen, uniq = set(), []
        for p in out:
            key = (_lc(p.get("partNumber","")), _lc(p.get("name","")))
            if key in seen: continue
            seen.add(key)
            uniq.append(p)
        return uniq

    def _build_indices(self):
        self.items = self.db.get("items", [])

    # ------------------ Public API ------------------

    def featured(self) -> List[Dict[str, Any]]:
        return self.items[:6]

    def search(self, query: str, part: Optional[str]=None, model: Optional[str]=None) -> List[Dict[str, Any]]:
        q = (part or query or "").strip()
        if not q:
            return []
        # exact part number first
        m = PARTNUM_RE.search(q)
        if m:
            pn = m.group(0).upper()
            exact = [p for p in self.items if _lc(p.get("partNumber","")) == _lc(pn)]
            if exact: return exact[:5]

        # scored search
        brand = _guess_brand(q)
        appl  = _guess_appliance(q)
        cat   = _guess_category(q)
        toks  = set(_tokens(q))

        scored = []
        for p in self.items:
            s = 0.05
            if brand and _lc(brand) in _lc(p.get("brand","")): s += 2.0
            if appl and appl in _lc(p.get("appliance","")): s += 2.5
            if cat and cat in _lc(p.get("category","")): s += 2.0
            name = _lc(p.get("name","")); desc = _lc(p.get("description",""))
            for t in toks:
                if t in name: s += 0.6
                if t in desc: s += 0.3
            if cat == "rack" and "rack" in name: s += 0.8
            if s >= 0.6: scored.append((s,p))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [p for _,p in scored][:5]
        if not results:
            # official fallback
            return [{
                "partNumber": "N/A",
                "name": f"No local results for '{query}'.",
                "description": "Try the official catalog.",
                "officialURL": f"https://www.partselect.com/Search.aspx?SearchTerm={q.replace(' ','+')}",
            }]
        return results

    def is_compatible(self, part: str, model: str) -> Tuple[bool,str]:
        part = (part or "").strip().upper()
        model = (model or "").strip().upper()
        if not part or not model:
            return False, "Please provide both a part number and a full model number."
        # try local part presence
        hit = next((p for p in self.items if _lc(p.get("partNumber","")) == _lc(part)), None)
        if hit and model in [m.upper() for m in hit.get("models",[])]:
            return True, f"✅ {part} fits model {model}."
        # fallback to official model search (list pages rarely include model tables)
        url = f"https://www.partselect.com/ModelSearch.aspx?SearchTerm={model}+{part}"
        tip = "Tip: model numbers are on the rating tag; include all suffix letters."
        if hit:
            brands = ", ".join(hit.get("brands",[]) or [])
            return False, f"Compatibility for {model} not confirmed locally (known brand(s): {brands or 'N/A'}). Check: {url}\n{tip}"
        return False, f"I couldn’t find {part} locally. Verify here: {url}"

    def install_guide(self, part: str, model: Optional[str]=None) -> str:
        part = (part or "").strip().upper()
        if not part:
            return "Please provide a part number (e.g., 'How to install WP2188656')."
        hit = next((p for p in self.items if _lc(p.get("partNumber","")) == _lc(part)), None)
        if hit and hit.get("installGuide"):
            return hit["installGuide"]
        url = f"https://www.partselect.com/Installation/{part}.htm"
        base = "1) Disconnect power/water\n2) Remove the faulty component\n3) Install replacement; restore and test"
        # small category-specific nuance
        if hit and "rack" in _lc(hit.get("category","")):
            base = "1) Disconnect power\n2) Remove rack; release clips/rollers/adjusters\n3) Seat and align replacement; test slide"
        return f"General guide for {part}:\n{base}"

    def find_parts(self, appliance_type=None, brand=None, category=None, query: Optional[str]=None) -> List[Dict[str, Any]]:
        # use same scored logic but allow explicit hints
        q = " ".join([x for x in [query or "", brand or "", appliance_type or "", category or ""] if x]).strip()
        res = self.search(q or (category or ""))
        if res and res[0].get("partNumber") != "N/A":
            # further filter if explicit appliance/brand/category given
            out = []
            for p in res:
                if appliance_type and appliance_type.lower() not in _lc(p.get("appliance","")): continue
                if brand and _lc(brand) not in _lc(p.get("brand","")): continue
                if category and _lc(category) not in _lc(p.get("category","")): continue
                out.append(p)
            return out or res
        # pass through fallback
        return res
