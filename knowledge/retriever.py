"""
knowledge/retriever.py

Hybrid retrieval over the internal knowledge base:
  1. Semantic search using FAISS + sentence-transformers (free, runs locally,
     no API key or cost — model downloads once from HuggingFace and is cached).
  2. Keyword search using BM25 (rank_bm25 library — free, pure Python).
  3. Scores from both are combined so the agent finds relevant knowledge
     even if the user's wording doesn't match the knowledge base exactly.

This is the "perceive the environment" part of the agent: before it reasons
or acts, it must pull in the real, internal facts it is allowed to use.
"""

import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base.json")

# all-MiniLM-L6-v2 is a small, free, local embedding model (~80MB, downloads once).
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


class KnowledgeRetriever:
    def __init__(self, data_path: str = DATA_PATH):
        with open(data_path, "r", encoding="utf-8") as f:
            self.documents = json.load(f)

        self.texts = [f"{d['topic']}: {d['content']}" for d in self.documents]

        # ---- Semantic (FAISS) index ----
        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        embeddings = self.embed_model.encode(self.texts, normalize_embeddings=True)
        embeddings = np.array(embeddings).astype("float32")

        self.index = faiss.IndexFlatIP(embeddings.shape[1])  # inner product = cosine on normalized vecs
        self.index.add(embeddings)

        # ---- Keyword (BM25) index ----
        tokenized_corpus = [t.lower().split() for t in self.texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def retrieve(self, query: str, top_k: int = 3):
        """Return top_k knowledge entries using a hybrid semantic + keyword score."""

        # Semantic scores
        query_vec = self.embed_model.encode([query], normalize_embeddings=True).astype("float32")
        sem_scores, sem_indices = self.index.search(query_vec, len(self.texts))
        sem_scores, sem_indices = sem_scores[0], sem_indices[0]

        # Normalize semantic scores to 0-1
        sem_map = {}
        if len(sem_scores) > 0:
            min_s, max_s = float(np.min(sem_scores)), float(np.max(sem_scores))
            for idx, score in zip(sem_indices, sem_scores):
                norm = (score - min_s) / (max_s - min_s + 1e-9)
                sem_map[int(idx)] = float(norm)

        # BM25 keyword scores, normalized to 0-1
        bm25_scores = self.bm25.get_scores(query.lower().split())
        max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0
        bm25_map = {i: score / max_bm25 for i, score in enumerate(bm25_scores)}

        # Combine: 60% semantic + 40% keyword (semantic generally more reliable for phrasing)
        combined = []
        for i in range(len(self.texts)):
            score = 0.6 * sem_map.get(i, 0.0) + 0.4 * bm25_map.get(i, 0.0)
            combined.append((i, score))

        combined.sort(key=lambda x: x[1], reverse=True)
        top = combined[:top_k]

        return [
            {
                "topic": self.documents[i]["topic"],
                "content": self.documents[i]["content"],
                "relevance_score": round(score, 3),
            }
            for i, score in top
        ]


if __name__ == "__main__":
    # Quick manual test
    retriever = KnowledgeRetriever()
    results = retriever.retrieve("my laptop is very slow")
    for r in results:
        print(r)
