import pytest

from app.application.ports import ProcessingCancelled
from app.domain.prompts import build_prompt_set
from app.infrastructure.ollama import (
    OllamaClient,
    OllamaError,
    OllamaTextProvider,
    chunk_text,
    clean_thinking_tags,
)


class Token:
    def __init__(self, cancelled=False):
        self.cancelled = cancelled

    def is_cancelled(self):
        return self.cancelled


THINK_OPEN = "<" + "think" + ">"
THINK_CLOSE = "</" + "think" + ">"


def test_clean_thinking_tags_removes_reasoning_noise():
    text = f"\x1b[2K\r{THINK_OPEN}hidden reasoning{THINK_CLOSE}Final answer"
    assert clean_thinking_tags(text) == "Final answer"
    assert clean_thinking_tags("") == ""


def test_chunk_text_splits_on_line_boundaries():
    text = "\n".join(f"line {index}" for index in range(100))
    chunks = chunk_text(text, 120)
    assert len(chunks) > 1
    assert all(len(chunk) <= 130 for chunk in chunks)
    assert " ".join(chunk for chunk in chunks).split() == text.split()
    assert chunk_text("short") == ("short",)
    assert chunk_text("   ") == ()


def test_generate_uses_http_response_and_cleans_output():
    calls = []

    def fake_request(url, payload, timeout):
        calls.append((url, payload))
        return {"response": f"{THINK_OPEN}noise{THINK_CLOSE}The answer", "thinking": "ignored"}

    client = OllamaClient(request_fn=fake_request)
    result = client.generate("llama3", "prompt")
    assert result == "The answer"
    assert calls[0][0] == "http://localhost:11434/api/generate"
    assert calls[0][1]["model"] == "llama3"
    assert calls[0][1]["stream"] is False
    assert calls[0][1]["options"]["num_predict"] == 4096


def test_generate_falls_back_to_cli_on_http_error(monkeypatch):
    def failing_request(url, payload, timeout):
        raise OSError("connection refused")

    client = OllamaClient(request_fn=failing_request)

    class FakeProcess:
        returncode = 0

        def poll(self):
            return 0

        def communicate(self):
            return (f"cli {THINK_OPEN}noise{THINK_CLOSE} answer", "")

    monkeypatch.setattr(
        "app.infrastructure.ollama.subprocess.Popen",
        lambda command, **kwargs: FakeProcess(),
    )
    assert " ".join(client.generate("llama3", "prompt").split()) == "cli answer"


def test_generate_cancelled_during_request():
    def hanging_request(url, payload, timeout):
        import time

        time.sleep(5)
        return {}

    client = OllamaClient(request_fn=hanging_request)
    with pytest.raises(ProcessingCancelled):
        client.generate("llama3", "prompt", cancel_token=Token(cancelled=True))


def test_summarize_chunks_long_transcript_and_combines():
    prompts = []

    def fake_request(url, payload, timeout):
        prompts.append(payload["prompt"])
        return {"response": f"partial {len(prompts)}"}

    provider = OllamaTextProvider(
        "llama3", client=OllamaClient(request_fn=fake_request), chunk_size=200
    )
    transcript = "\n".join(f"sentence {index} with some padding text" for index in range(30))
    result = provider.summarize(transcript, "tr")
    assert result.startswith("partial ")
    assert len(prompts) >= 3
    assert "Partial summaries:" in prompts[-1]


def test_summarize_single_chunk_skips_combine():
    prompts = []

    def fake_request(url, payload, timeout):
        prompts.append(payload["prompt"])
        return {"response": "final summary"}

    provider = OllamaTextProvider(
        "llama3", client=OllamaClient(request_fn=fake_request), chunk_size=5000
    )
    assert provider.summarize("short transcript", "en") == "final summary"
    assert len(prompts) == 1
    assert "Transcript:" in prompts[0]


def test_extract_highlights_uses_srt_content():
    def fake_request(url, payload, timeout):
        return {
            "response": (
                '[{"start":"00:01:23","end":"00:01:40","title":"important moment",'
                '"score":8,"reason":"explicit commitment"}]'
            )
        }

    provider = OllamaTextProvider("llama3", client=OllamaClient(request_fn=fake_request))
    result = provider.extract_highlights("1\n00:00:00,000 --> 00:00:01,000\nHello\n", "en")
    assert result == "- 00:01:23 important moment"


def test_extract_highlights_empty_content_raises():
    provider = OllamaTextProvider(
        "llama3", client=OllamaClient(request_fn=lambda url, payload, timeout: {})
    )
    with pytest.raises(OllamaError, match="empty"):
        provider.extract_highlights("   ", "en")


def test_text_provider_uses_injected_prompt_set():
    seen = []

    def fake_request(url, payload, timeout):
        seen.append(payload["prompt"])
        return {"response": "summary"}

    custom = build_prompt_set({"summary": "CUSTOM:{lang}:{transcript}"})
    provider = OllamaTextProvider(
        "llama3", client=OllamaClient(request_fn=fake_request), prompts=custom
    )
    assert provider.summarize("hello world", "tr") == "summary"
    assert seen == ["CUSTOM:tr:hello world"]
