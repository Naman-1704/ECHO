"""
Quick sanity check — run this BEFORE trying full ingestion, to confirm Ollama,
ChromaDB, and the extraction prompt all work correctly on your machine.

Usage:
    python scripts/test_local_llm.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai.llm_client import chat_completion
from app.ai.extraction import extract_structured_facts
from app.ai.embeddings import embed_text
from app.db.vector_store import add_chunk_embedding, _collection

SAMPLE_EMAIL = """
Hi team, following up on the Atlas migration project. After discussing with Priya
and the infra team, we've decided to move forward with the phased rollout approach
instead of a big-bang cutover, mainly because it lets us roll back per-service if
something breaks. Rahul is going to own the staging environment setup — still
pending as of this email. We should have a decision on the vendor for the logging
pipeline by end of next week.
"""

print("1. Testing basic chat completion...")
result = chat_completion("Reply with exactly the word: OK", max_tokens=10)
print(f"   Response: {result!r}")
assert result.strip(), "Got empty response — is Ollama running? (ollama serve)"
print("   PASS\n")

print("2. Testing embedding generation...")
vec = embed_text("test sentence")
print(f"   Embedding length: {len(vec)} (should be 384)")
assert len(vec) == 384
print("   PASS\n")

print("3. Testing structured extraction on a sample email...")
extracted = extract_structured_facts(SAMPLE_EMAIL)
print(f"   Extracted: {extracted}")
assert "people" in extracted and not extracted.get("_parse_error"), "Extraction failed to produce valid JSON"
print("   PASS\n")

print("4. Testing ChromaDB round-trip (write + query)...")
add_chunk_embedding(
    chunk_id="smoke-test-chunk",
    user_id="smoke-test-user",
    raw_item_id="smoke-test-item",
    text=SAMPLE_EMAIL,
    embedding=vec,
)
result = _collection.query(query_embeddings=[vec], n_results=1, where={"user_id": "smoke-test-user"})
print(f"   Retrieved id: {result['ids'][0]}")
assert result["ids"][0] == ["smoke-test-chunk"], "Chroma didn't return the chunk we just wrote"
_collection.delete(ids=["smoke-test-chunk"])  # clean up the test row
print("   PASS\n")

print("All checks passed — safe to run full ingestion now.")
