"""Chunk runbooks by section, embed them and load them into Qdrant."""
import re
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

import os

RUNBOOKS = Path(os.environ.get("ARGUS_RUNBOOK_DIR", Path(__file__).parent / "runbooks"))
COLLECTION = os.environ.get("ARGUS_COLLECTION", "runbooks")  # per-client vector collection
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
QDRANT_URL = "http://localhost:6333"

_embedder = None


def embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBED_MODEL, device="cpu")
    return _embedder


def load_chunks() -> list[dict]:
    chunks = []
    for path in sorted(RUNBOOKS.glob("RB-*.md")):
        text = path.read_text()
        rid = re.search(r"^id: (RB-\d+)", text, re.M).group(1)
        title = re.search(r"^title: (.+)$", text, re.M).group(1)
        for m in re.finditer(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
            body = m.group(2).strip()
            chunks.append({"runbook_id": rid, "title": title, "section": m.group(1), "text": body})
    return chunks


def build_index(url: str = QDRANT_URL) -> int:
    client = QdrantClient(url=url, check_compatibility=False)
    chunks = load_chunks()
    # the title is embedded with each section so a short section still carries its topic
    vectors = embedder().encode([f"{c['title']}. {c['section']}: {c['text']}" for c in chunks], normalize_embeddings=True)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE))
    client.upsert(COLLECTION, [PointStruct(id=i, vector=v.tolist(), payload=c) for i, (v, c) in enumerate(zip(vectors, chunks))])
    return len(chunks)


if __name__ == "__main__":
    print(f"indexed {build_index()} chunks")
