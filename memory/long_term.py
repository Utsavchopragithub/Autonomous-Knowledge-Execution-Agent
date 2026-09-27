"""
memory/long_term.py

Short-term memory (audit_log.get_recent_interactions) only remembers the
last few interactions in order -- that's fine for "what did we just talk
about" but it's not real long-term memory. If an employee asked about the
password policy 3 weeks and 50 interactions ago, "recent" won't find it.

This module embeds every past interaction and searches them SEMANTICALLY,
the same way we search the knowledge base -- so the agent can recall any
relevant past exchange, not just the newest ones.

Rebuilt fresh at agent startup from the SQLite audit log (cheap at this
scale). In a larger system you'd persist and incrementally update the
index instead of rebuilding it every run.
"""

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from memory.audit_log import get_all_interactions_for_memory

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


class LongTermMemory:
    def __init__(self):
        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        self.refresh()

    def refresh(self):
        """Rebuild the memory index from whatever is currently in the audit log."""
        rows = get_all_interactions_for_memory()
        self.entries = [
            {
                "query": q,
                "summary": f"Q: {q} -> action: {action} -> result: {result}",
            }
            for q, action, result in rows
        ]

        if not self.entries:
            self.index = None
            return

        texts = [e["summary"] for e in self.entries]
        embeddings = self.embed_model.encode(texts, normalize_embeddings=True).astype("float32")
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)

    def recall(self, query: str, top_k: int = 3):
        """Return the most semantically relevant past interactions, however old."""
        if not self.entries or self.index is None:
            return []

        query_vec = self.embed_model.encode([query], normalize_embeddings=True).astype("float32")
        scores, indices = self.index.search(query_vec, min(top_k, len(self.entries)))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if score > 0.3:  # only surface genuinely relevant memories
                results.append(self.entries[int(idx)]["summary"])
        return results