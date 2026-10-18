from functools import lru_cache

# Local, free, no API key needed — good for MVP/dev. 384-dim output.
# If you later want higher quality, swap for another model, but remember to re-embed
# everything already stored in ChromaDB (dimensions must match).
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    # Imported lazily: sentence-transformers pulls in torch, which takes seconds to import.
    # Deferring it keeps API startup fast and lets tests run without the heavy dependency.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vectors]
