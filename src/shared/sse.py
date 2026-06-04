import json
import time


def make_chunk(text: str, model_id: str, completion_id: str) -> str:
    """Format a text fragment as an OpenAI-compatible SSE chunk."""
    data = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }
    return f"data: {json.dumps(data)}\n\n"


def done_chunk() -> str:
    """Return the SSE stream termination sentinel."""
    return "data: [DONE]\n\n"


def new_completion_id() -> str:
    return f"chatcmpl-{int(time.time() * 1000)}"
