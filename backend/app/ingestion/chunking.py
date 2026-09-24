def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """
    Simple word-based sliding-window chunker. Good enough for MVP;
    most emails will be a single chunk anyway. chunk_size/overlap are in words.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start = end - overlap  # step back for overlap
    return chunks
