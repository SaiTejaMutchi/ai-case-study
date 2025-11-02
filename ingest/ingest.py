import os, json, argparse
from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss, numpy as np

def chunk_text(text, chunk_size=600, overlap=80):
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i+chunk_size])
        out.append(chunk)
        i += (chunk_size - overlap)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=str, default='../data')
    ap.add_argument('--index_dir', type=str, default='../backend/index')
    ap.add_argument('--model', type=str, default='sentence-transformers/all-MiniLM-L6-v2')
    args = ap.parse_args()

    os.makedirs(args.index_dir, exist_ok=True)
    meta_path = Path(args.index_dir) / "meta.json"
    index_path = Path(args.index_dir) / "faiss.index"

    emb = SentenceTransformer(args.model)
    all_texts = []
    meta = []

    # Load any .txt or .json knowledge
    for p in Path(args.input).rglob('*'):
        if p.suffix.lower() == '.txt':
            text = p.read_text(encoding='utf-8', errors='ignore')
            for ch in chunk_text(text):
                all_texts.append(ch)
                meta.append({"id": len(meta)+1, "source": str(p), "text": ch})
        elif p.suffix.lower() == '.json':
            try:
                data = json.loads(p.read_text(encoding='utf-8', errors='ignore'))
                # add product descriptions
                items = data.get("items", [])
                for it in items:
                    t = f"{it.get('name')} ({it.get('partNumber')}) - models: {', '.join(it.get('models', []))}. " + it.get("installGuide","")
                    all_texts.append(t)
                    meta.append({"id": len(meta)+1, "source": str(p), "text": t})
            except Exception:
                pass

    if not all_texts:
        print("No texts found to index.")
        return

    X = emb.encode(all_texts, normalize_embeddings=True)
    X = np.array(X, dtype='float32')
    index = faiss.IndexFlatIP(X.shape[1])
    index.add(X)

    faiss.write_index(index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Indexed {len(all_texts)} chunks into {index_path}")

if __name__ == '__main__':
    main()
