"""
knowledge/retriever.py

Same hybrid FAISS + BM25 idea as before, but now built over documents
pulled from ALL FOUR knowledge sources at once (knowledge/sources.py):
JSON policies, CSV ticket history, SQL employee database, and chunked
unstructured handbook text. Every retrieved result carries a "source"
label so the agent (and the person reading the output) knows exactly
where a fact came from -- important for spotting when two sources
disagree (see agent/planner.py for how conflicts get handled).
"""

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from knowledge.sources import load_all_sources

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


class KnowledgeRetriever:
    def __init__(self):
        self.documents = load_all_sources()
        self.texts = [d["text"] for d in self.documents]

        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        embeddings = self.embed_model.encode(self.texts, normalize_embeddings=True)
        embeddings = np.array(embeddings).astype("float32")

        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)

        tokenized_corpus = [t.lower().split() for t in self.texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def retrieve(self, query: str, top_k: int = 5):
        query_vec = self.embed_model.encode([query], normalize_embeddings=True).astype("float32")
        sem_scores, sem_indices = self.index.search(query_vec, len(self.texts))
        sem_scores, sem_indices = sem_scores[0], sem_indices[0]

        sem_map = {}
        if len(sem_scores) > 0:
            min_s, max_s = float(np.min(sem_scores)), float(np.max(sem_scores))
            for idx, score in zip(sem_indices, sem_scores):
                norm = (score - min_s) / (max_s - min_s + 1e-9)
                sem_map[int(idx)] = float(norm)

        bm25_scores = self.bm25.get_scores(query.lower().split())
        max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0
        bm25_map = {i: score / max_bm25 for i, score in enumerate(bm25_scores)}

        combined = []
        for i in range(len(self.texts)):
            score = 0.6 * sem_map.get(i, 0.0) + 0.4 * bm25_map.get(i, 0.0)
            combined.append((i, score))

        combined.sort(key=lambda x: x[1], reverse=True)
        top = combined[:top_k]

        return [
            {
                "text": self.documents[i]["text"],
                "source": self.documents[i]["source"],
                "relevance_score": round(score, 3),
            }
            for i, score in top
            if score > 0.05
        ]


if __name__ == "__main__":
    r = KnowledgeRetriever()
    for res in r.retrieve("how many leave days do I get"):
        print(res)