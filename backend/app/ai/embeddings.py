from functools import lru_cache
from sentence_transformers import SentenceTransformer

# Local, free, no API key needed — good for MVP/dev. 384-dim output.
# If you later want higher quality, swap for an API-based embedding model,
# but remember to update EMBEDDING_DIM in db/models.py and re-embed everything.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vectors]
