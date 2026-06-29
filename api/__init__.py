from .anthropic import stream_completion as anthropic_stream_completion
from .lm_studio import stream_completion as lm_studio_stream_completion
from .openai import stream_completion as openai_stream_completion


def get_stream_completion(provider, endpoint):
    provider = (provider or "auto").strip().lower()
    clean = (endpoint or "").rstrip("/").lower()

    if provider == "lm_studio":
        return lm_studio_stream_completion

    if provider == "openai":
        return openai_stream_completion

    if provider == "anthropic":
        return anthropic_stream_completion

    if clean.endswith("/api/v1/chat"):
        return lm_studio_stream_completion

    if clean.endswith("/v1/messages") or "/v1/messages" in clean or "anthropic" in clean:
        return anthropic_stream_completion

    return openai_stream_completion