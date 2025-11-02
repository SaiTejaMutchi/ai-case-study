"""
create_catalog_json.py
----------------------
Scrapes saved PartSelect HTML pages (Dishwasher + Refrigerator)
and produces two clean JSON files:

  • parts_catalog.json
  • symptom_mapping.json

Each part includes:
  category, name, partNumber, manufacturerPart, price, stock,
  description, symptoms, installation, imageUrl, and source.
"""

import re
import json
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

# === Input HTML files ===
DISHWASHER_HTML = "Official Dishwasher Parts _ Order Today, Ships Today _ PartSelect.html"
REFRIGERATOR_HTML = "Official Refrigerator Parts _ Order Today, Ships Today _ PartSelect.html"

# === Stop words/markers for parsing sections ===
STOP_WORDS = ("Fixes these symptoms", "Installation Instructions", "Installation")
STOP_CLASSES = ("nf__part__detail__symptoms", "nf__part__detail__instruction")


# ---------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------
def find_mfg_div(block: Tag) -> Tag | None:
    """Find the <div> that contains 'Manufacturer Part Number'."""
    for div in block.find_all("div", class_=re.compile("nf__part__detail__part-number")):
        if "Manufacturer Part Number" in div.get_text(" ", strip=True):
            return div
    # Fallback
    return block.find(
        lambda t: (
            isinstance(t, Tag)
            and t.name == "div"
            and re.search(r"\bManufacturer\s+Part\s+Number\b", t.get_text(" ", strip=True), re.I)
        )
    )


def is_stop_node(node: Tag) -> bool:
    """Identify a node that marks the end of the description section."""
    if not isinstance(node, Tag):
        return False
    txt = node.get_text(" ", strip=True)
    if any(s in txt for s in STOP_WORDS):
        return True
    cls = " ".join(node.get("class", []))
    if any(s in cls for s in STOP_CLASSES):
        return True
    node_id = (node.get("id") or "")
    if re.search(r"_(Symptoms|RepairStory)$", node_id):
        return True
    return False


def extract_description(block: Tag) -> str:
    """Extract description text after Manufacturer Part Number."""
    mfg = find_mfg_div(block)
    if not mfg:
        text = block.get_text(" ", strip=True)
        m = re.search(r"PartSelect Number\s+PS\d{4,8}(.*?)(Fixes these symptoms|Installation|$)", text, re.I)
        if m and m.group(1).strip():
            desc = re.sub(r"\s{2,}", " ", m.group(1)).strip()
            return desc if desc else "No detailed description available."
        return "No detailed description available."

    chunks: list[str] = []
    for el in mfg.next_elements:
        if isinstance(el, Tag) and is_stop_node(el):
            break
        if isinstance(el, NavigableString):
            s = str(el).strip()
            if s and len(s) > 3 and "PartSelect Number" not in s:
                chunks.append(s)
        elif isinstance(el, Tag) and el.name in ("p", "span"):
            s = el.get_text(" ", strip=True)
            if s and len(s) > 3:
                chunks.append(s)
    desc = " ".join(chunks)
    return re.sub(r"\s{2,}", " ", desc).strip() or "No detailed description available."


def extract_installation(card: Tag) -> str | None:
    """Extract installation instructions if present."""
    header = card.find("div", id=re.compile(r"_RepairStory$"))
    if not header:
        return None

    creator_div = header.find_next("div", class_=re.compile("instruction__creator"))
    quote_div = header.find_next("div", class_=re.compile("instruction__quote"))

    creator = creator_div.get_text(" ", strip=True) if creator_div else None
    summary = quote_div.find("div", class_="bold").get_text(" ", strip=True) if quote_div else None
    details = quote_div.find("span").get_text(" ", strip=True) if quote_div else None

    parts = []
    if creator:
        parts.append(f"Contributor: {creator}")
    if summary:
        parts.append(f"Issue: {summary}")
    if details:
        parts.append(f"Steps: {details}")

    return " ".join(parts) if parts else None


# ---------------------------------------------------------------------
# Core Parser
# ---------------------------------------------------------------------
def parse_html(file_path: str, category: str):
    print(f"\n🔍 Parsing {category} → {Path(file_path).name}")

    try:
        html_text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"❌ ERROR: Could not read {file_path}: {e}")
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    items, seen = [], set()
    re_part = re.compile(r"PS\d{4,8}")
    re_price = re.compile(r"\$\s?\d{1,4}\.\d{2}")
    re_stock = re.compile(r"(In Stock|Out of Stock)", re.I)

    product_blocks = soup.select("div.nf__part") or soup.select("div.nf__part__left-col")
    if not product_blocks:
        print(f"⚠️ No product containers found in {Path(file_path).name}")
        return []

    for block in product_blocks:
        card = block if "nf__part" in block.get("class", []) else block.find_parent("div", class_="nf__part")
        if not card:
            continue

        text = card.get_text(" ", strip=True)
        if not text or "PartSelect Number" not in text:
            continue

        ps_match = re_part.search(text)
        if not ps_match:
            continue
        part_number = ps_match.group(0).upper()
        if part_number in seen:
            continue
        seen.add(part_number)

        manufacturer = None
        mfg_div = find_mfg_div(card)
        if mfg_div:
            strong_tag = mfg_div.find("strong")
            manufacturer = strong_tag.get_text(strip=True) if strong_tag else None

        description = extract_description(card)

        # Image + name
        name, image_url = None, None
        img_tag = card.find("img")
        if img_tag:
            src = img_tag.get("src", "") or img_tag.get("data-src", "")
            title = img_tag.get("title") or img_tag.get("alt") or ""
            if title and "Part Number" in title:
                name = title.split("– Part Number")[0].strip(" –")
            elif title and not any(x in title.lower() for x in ["model", "locator", "search"]):
                name = title.strip()
            if src and not src.startswith("data:") and not any(
                x in src.lower() for x in ["searchbox", "icon", "locator", "sprite", "flag", "badge"]
            ):
                image_url = src

        if not name:
            title_link = card.find("a", class_="nf__part__detail__title")
            if title_link:
                name = title_link.get_text(" ", strip=True)
            else:
                name = "Unnamed Part"

        price_match = re_price.search(text)
        price_val = float(price_match.group(0).replace("$", "").strip()) if price_match else None

        stock_match = re_stock.search(text)
        stock = stock_match.group(1).strip() if stock_match else "Unknown"

        # Symptoms
        symptoms = []
        sym_section = card.find(string=re.compile("Fixes these symptoms", re.I))
        if sym_section:
            ul = sym_section.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    val = li.get_text(strip=True)
                    if "See more" not in val:
                        symptoms.append(val)

        installation = extract_installation(card)

        if any(bad in name.lower() for bad in ["model number locator", "search", "locator"]):
            continue

        items.append({
            "category": category,
            "name": name.strip(),
            "partNumber": part_number,
            "manufacturerPart": manufacturer or part_number,
            "price": price_val,
            "stock": stock,
            "description": description,
            "symptoms": symptoms,
            "installation": installation,
            "imageUrl": image_url,
            "source": Path(file_path).name
        })

    print(f"✅ Extracted {len(items)} {category.lower()} parts from {Path(file_path).name}")
    return items


# ---------------------------------------------------------------------
# Symptom Mapping
# ---------------------------------------------------------------------
def create_symptom_mapping(parts_list: list[dict]) -> dict:
    print("\n🔍 Creating symptom-to-part mapping...")
    symptom_map = {}
    for part in parts_list:
        pn = part.get("partNumber")
        if not pn:
            continue
        for symptom_text in part.get("symptoms", []):
            key = symptom_text.lower().strip().replace("’", "'")
            if not key:
                continue
            if key not in symptom_map:
                symptom_map[key] = {
                    "guidance": f"This problem could be related to '{key}'. Common parts to check include the following:",
                    "parts": []
                }
            if pn not in symptom_map[key]["parts"]:
                symptom_map[key]["parts"].append(pn)
    print(f"✅ Mapped {len(symptom_map)} unique symptoms.")
    return symptom_map


# ---------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------
def main():
    dishwasher_parts = parse_html(DISHWASHER_HTML, "Dishwasher")
    refrigerator_parts = parse_html(REFRIGERATOR_HTML, "Refrigerator")
    combined = dishwasher_parts + refrigerator_parts

    seen, final = set(), []
    for p in combined:
        if p["partNumber"] not in seen:
            seen.add(p["partNumber"])
            final.append(p)

    # Metadata summary
    meta = {
        "total_parts": len(final),
        "categories": {
            "Dishwasher": len(dishwasher_parts),
            "Refrigerator": len(refrigerator_parts),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }

    out_data = {"meta": meta, "items": final}

    # Write outputs
    out_path = Path("parts_catalog.json")
    out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"\n✅ Saved {len(final)} total parts → {out_path.resolve()}")

    symptom_map = create_symptom_mapping(final)
    symptom_path = Path("symptom_mapping.json")
    symptom_path.write_text(json.dumps(symptom_map, indent=2), encoding="utf-8")
    print(f"✅ Saved symptom mapping → {symptom_path.resolve()}")


if __name__ == "__main__":
    main()
