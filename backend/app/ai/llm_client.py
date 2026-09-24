import ollama

from app.config import settings

_client = ollama.Client(host=settings.ollama_base_url)


def chat_completion(prompt: str, max_tokens: int = 800, force_json: bool = False) -> str:
    """
    Single entry point for all LLM calls in the app. Both extraction.py and chat.py
    call this — swapping models or providers later (e.g. back to a hosted API) means
    changing this one file, not every caller.
    """
    response = _client.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": prompt}],
        format="json" if force_json else None,
        options={
            "num_predict": max_tokens,
            "temperature": 0.2,   # low temperature — we want consistent, grounded output, not creativity
        },
    )
    return response["message"]["content"]
