import json
import urllib.error
from pathlib import Path

import pytest

from app.domain.prompts import build_prompt_set
from app.infrastructure.cloud_policy import CloudPolicyViolation
from app.infrastructure.openai_compat import (
    OpenAICompatClient,
    OpenAICompatError,
    OpenAICompatKeyError,
    OpenAICompatTextProvider,
    OpenAICompatVisionProvider,
    extract_text,
    infer_vision_capable,
)


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, payload, timeout, headers):
        self.calls.append((url, payload, headers))
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok_response(text="answer", **usage):
    response = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
    if usage:
        response["usage"] = usage
    return response


def http_error(code):
    return urllib.error.HTTPError("https://example.test/x", code, "err", None, None)


def make_client(transport, **kwargs):
    params = {
        "model": "m",
        "base_url": "https://example.test/v1",
        "provider": "openrouter",
        "key_getter": lambda: "sk-test-key",
        "transport_fn": transport,
        "min_interval": 0,
    }
    params.update(kwargs)
    return OpenAICompatClient(**params)


def test_missing_key_raises_without_request():
    transport = RecordingTransport([])
    client = make_client(transport, key_getter=lambda: None)
    with pytest.raises(OpenAICompatKeyError):
        client.generate([{"type": "text", "text": "hi"}])
    assert transport.calls == []


def test_generate_sends_bearer_header_and_text_only():
    transport = RecordingTransport([ok_response("summary")])
    client = make_client(transport)
    assert client.generate([{"type": "text", "text": "hello"}]) == "summary"
    url, payload, headers = transport.calls[0]
    assert url == "https://example.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test-key"
    assert payload["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    assert "video" not in json.dumps(payload).lower()


def test_auth_error_is_immediate():
    transport = RecordingTransport([http_error(401)])
    client = make_client(transport, max_retries=3)
    with pytest.raises(OpenAICompatError, match="rejected the API key"):
        client.generate([{"type": "text", "text": "hi"}])
    assert len(transport.calls) == 1  # never retried


def test_rate_limit_retries_then_succeeds():
    transport = RecordingTransport([http_error(429), ok_response("ok")])
    sleeps = []
    client = make_client(transport, sleep_fn=sleeps.append, max_retries=2)
    assert client.generate([{"type": "text", "text": "hi"}]) == "ok"
    assert len(transport.calls) == 2
    assert sleeps == [8.0]


def test_usage_accumulates_and_counts_images():
    transport = RecordingTransport(
        [
            ok_response("a", prompt_tokens=10, completion_tokens=4),
            ok_response("b", prompt_tokens=3, completion_tokens=1),
        ]
    )
    client = make_client(transport)
    client.generate([{"type": "text", "text": "x"}])
    client.generate(
        [
            {"type": "text", "text": "y"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]
    )
    assert client.usage.input_tokens == 13
    assert client.usage.output_tokens == 5
    assert client.usage.images == 1
    assert client.usage.requests == 2


def test_text_provider_uses_prompt_set():
    transport = RecordingTransport([ok_response("s")])
    client = make_client(transport)
    provider = OpenAICompatTextProvider(
        "m", client=client, prompts=build_prompt_set({"summary": "CUSTOM {lang} {transcript}"})
    )
    provider.summarize("hello", "tr")
    content = transport.calls[0][1]["messages"][0]["content"]
    assert content[0]["text"] == "CUSTOM tr hello"


def test_vision_provider_refuses_video_file():
    transport = RecordingTransport([])
    provider = OpenAICompatVisionProvider("m", client=make_client(transport))
    with pytest.raises(CloudPolicyViolation, match="never sent"):
        provider.analyze_frame(Path("clip.mp4"), "ctx", "task", "en")
    assert transport.calls == []


def test_vision_provider_sends_image_url(tmp_path):
    frame = tmp_path / "scene.png"
    frame.write_bytes(b"png-bytes")
    transport = RecordingTransport([ok_response("described")])
    provider = OpenAICompatVisionProvider("m", client=make_client(transport))
    assert provider.analyze_frame(frame, "ctx", "task", "tr") == "described"
    content = transport.calls[0][1]["messages"][0]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "video/" not in json.dumps(transport.calls[0][1]).lower()


def test_infer_vision_capable_prefers_metadata():
    item = {"id": "x", "architecture": {"input_modalities": ["text", "image"]}}
    assert infer_vision_capable(item) is True
    text_only = {"id": "x", "architecture": {"input_modalities": ["text"]}}
    assert infer_vision_capable(text_only) is False
    assert infer_vision_capable({"id": "llava-13b"}) is True
    assert infer_vision_capable({"id": "qwen-coder"}) is False


def test_extract_text_variants():
    assert extract_text(ok_response("hello")) == "hello"
    with pytest.raises(OpenAICompatError, match="no choices"):
        extract_text({})
    with pytest.raises(OpenAICompatError, match="finish_reason"):
        extract_text({"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
