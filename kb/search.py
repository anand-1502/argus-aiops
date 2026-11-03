"""Hybrid retrieval: dense search in Qdrant, then a cross-encoder rerank."""
from qdrant_client import QdrantClient

from kb.index import COLLECTION, QDRANT_URL, embedder

RERANK_MODEL = "BAAI/bge-reranker-base"


class Searcher:
    def __init__(self, url: str = QDRANT_URL, candidates: int = 12):
        from sentence_transformers import CrossEncoder

        self.client = QdrantClient(url=url, check_compatibility=False)
        self.reranker = CrossEncoder(RERANK_MODEL, device="cpu")
        self.candidates = candidates

    def search(self, query: str, k: int = 3) -> list[dict]:
        vec = embedder().encode(query, normalize_embeddings=True).tolist()
        found = self.client.query_points(COLLECTION, query=vec, limit=self.candidates, with_payload=True).points
        if not found:
            return []
        scores = self.reranker.predict([(query, f"{p.payload['title']}. {p.payload['section']}: {p.payload['text']}") for p in found])
        ranked = sorted(zip(found, scores), key=lambda x: x[1], reverse=True)[:k]
        return [
            {**p.payload, "score": float(s), "citation": f"{p.payload['runbook_id']}#{p.payload['section']}"}
            for p, s in ranked
        ]
