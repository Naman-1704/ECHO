import json
from pathlib import Path

from app.ai.llm_client import chat_completion

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "extraction_prompt.txt").read_text()


def extract_structured_facts(chunk_text: str) -> dict:
    """
    Calls the local model to pull people/projects/decisions/action_items out of one chunk.
    force_json=True makes Ollama constrain output to valid JSON, which matters a lot more
    for local models than hosted ones — without it, smaller models drift into extra prose
    around the JSON fairly often. Returns a safe empty structure on parse failure rather
    than crashing the whole ingestion job.
    """
    prompt = _PROMPT_TEMPLATE.format(chunk_text=chunk_text)
    raw = chat_completion(prompt, max_tokens=1000, force_json=True).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"people": [], "projects": [], "decisions": [], "action_items": [], "_parse_error": True}
