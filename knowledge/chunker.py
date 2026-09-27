"""
knowledge/chunker.py

Unstructured text (a raw handbook, a long email, a PDF dump) can't be
embedded as one giant blob — it's too long and mixes many topics, so
semantic search over it would be vague. The standard fix is CHUNKING:
split it into overlapping windows of ~N words so each chunk stays focused
on one idea, and overlap prevents a sentence from being awkwardly cut in
half at a chunk boundary.
"""


def chunk_text(text: str, chunk_size_words: int = 90, overlap_words: int = 15):
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size_words
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start = end - overlap_words  # step back so chunks overlap
    return chunks