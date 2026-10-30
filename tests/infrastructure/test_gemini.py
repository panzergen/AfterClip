import base64
import json
import urllib.error
from pathlib import Path

import pytest

from app.domain.prompts import build_prompt_set
from app.infrastructure.gemini import (
    CloudPolicyViolation,
    GeminiClient,
    GeminiError,
    GeminiKeyMissing,
    GeminiTextProvider,
    GeminiVisionProvider,
    inline_data_part,
)
from app.infrastructure.gemini.client import extract_text
from app.infrastructure.logging_filter import REDACTED, SECRET_REDACTOR


class RecordingRequest:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, payload, timeout):
        self.calls.append((url, payload, timeout))
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok_response(text="answer"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def http_error(code):
    return urllib.error.HTTPError(
        "https://generativelanguage.googleapis.com/x", code, "err", None, None
    )


def test_inline_data_part_rejects_video_mime():
    with pytest.raises(CloudPolicyViolation):
        inline_data_part("video/mp4", b"video-bytes")
    with pytest.raises(CloudPolicyViolation):
        inline_data_part("application/octet-stream", b"x")


def test_vision_provider_refuses_video_files_without_any_request():
    request = RecordingRequest([])
    provider = GeminiVisionProvider(client=GeminiClient(key_getter=lambda: "k", request_fn=request))
    video = Path("clip.mp4")
    with pytest.raises(CloudPolicyViolation, match="never sent"):
        provider.analyze_frame(video, "context", "task", "tr")
    assert request.calls == []


def test_text_provider_sends_only_text_parts():
    sleeps = []
    request = RecordingRequest(
        [ok_response("partial one"), ok_response("partial two"), ok_response("final summary")]
    )
    provider = GeminiTextProvider(
        key_getter=lambda: "sk-gemini-test-key",
        request_fn=request,
        sleep_fn=sleeps.append,
        min_interval=0,
    )
    summary = provider.summarize("a" * 5000, "tr")
    assert summary == "final summary"
    assert len(request.calls) == 3  # two chunk summaries + combine
    for url, payload, _timeout in request.calls:
        assert "generativelanguage.googleapis.com" in url
        parts = payload["contents"][0]["parts"]
        assert all(set(part) == {"text"} for part in parts)
        assert "video/" not in json.dumps(payload).lower()
    assert sleeps == []


def test_vision_payload_contains_only_png_inline_data(tmp_path):
    request = RecordingRequest([ok_response("frame described")])
    provider = GeminiVisionProvider(
        client=GeminiClient(key_getter=lambda: "sk-gemini-test-key", request_fn=request)
    )
    frame = tmp_path / "scene_00h00m02s.png"
    frame.write_bytes(b"\x89PNG-fake-bytes")
    result = provider.analyze_frame(frame, "spoken words", "task", "tr")
    assert result == "frame described"
    _url, payload, _timeout = request.calls[0]
    parts = payload["contents"][0]["parts"]
    assert parts[0]["text"].startswith("This frame is from a screen recording")
    inline = parts[1]["inline_data"]
    assert inline["mime_type"] == "image/png"
    assert base64.b64decode(inline["data"]) == b"\x89PNG-fake-bytes"
    # No video MIME type or binary ever enters the payload (T18b/T18c)
    assert "video/" not in json.dumps(payload).lower()


def test_vision_prompt_override_is_used_verbatim(tmp_path):
    request = RecordingRequest([ok_response("frame described")])
    provider = GeminiVisionProvider(
        client=GeminiClient(key_getter=lambda: "sk-gemini-test-key", request_fn=request)
    )
    frame = tmp_path / "scene_00h00m02s.png"
    frame.write_bytes(b"\x89PNG-fake-bytes")
    provider.analyze_frame(
        frame, "spoken words", "task", "tr", prompt="FALLBACK SCREEN PROMPT"
    )
    parts = request.calls[0][1]["contents"][0]["parts"]
    assert parts[0]["text"] == "FALLBACK SCREEN PROMPT"


def test_retry_on_rate_limit_then_success():
    sleeps = []
    request = RecordingRequest([http_error(429), http_error(429), ok_response("recovered")])
    client = GeminiClient(
        key_getter=lambda: "k",
        request_fn=request,
        sleep_fn=sleeps.append,
        max_retries=3,
        min_interval=0,
    )
    assert client.generate([{"text": "hi"}]) == "recovered"
    assert sleeps == [8.0, 16.0]


def test_retry_is_bounded_and_raises_when_exhausted():
    sleeps = []
    request = RecordingRequest([http_error(503)] * 4)
    client = GeminiClient(
        key_getter=lambda: "k",
        request_fn=request,
        sleep_fn=sleeps.append,
        max_retries=2,
        min_interval=0,
    )
    with pytest.raises(GeminiError, match="Gemini request failed"):
        client.generate([{"text": "hi"}])
    assert len(request.calls) == 3  # initial + 2 retries, never infinite
    assert sleeps == [2.0, 4.0]


def test_requests_are_throttled_to_min_interval():
    now = [100.0]
    sleeps = []

    def clock():
        return now[0]

    def fake_sleep(seconds):
        now[0] += seconds
        sleeps.append(seconds)

    request = RecordingRequest([ok_response("one"), ok_response("two"), ok_response("three")])

    def serving_request(url, payload, timeout):
        now[0] += 1.0  # each request takes 1s of clock time
        return request(url, payload, timeout)

    client = GeminiClient(
        key_getter=lambda: "k",
        request_fn=serving_request,
        sleep_fn=fake_sleep,
        clock_fn=clock,
        min_interval=4.0,
    )
    client.generate([{"text": "a"}])  # finishes at t=101, gap measured from request end
    client.generate([{"text": "b"}])  # waits the full 4s after finish -> t->106
    client.generate([{"text": "c"}])  # waits 4s again -> t->111
    assert sleeps == [4.0, 4.0]


def test_auth_error_fails_immediately_without_retry():
    sleeps = []
    request = RecordingRequest([http_error(401)])
    client = GeminiClient(
        key_getter=lambda: "k", request_fn=request, sleep_fn=sleeps.append, max_retries=3
    )
    with pytest.raises(GeminiError):
        client.generate([{"text": "hi"}])
    assert len(request.calls) == 1
    assert sleeps == []


def test_model_404_gives_actionable_error_without_retry():
    request = RecordingRequest([http_error(404)])
    client = GeminiClient(
        key_getter=lambda: "k", request_fn=request, sleep_fn=lambda _s: None, max_retries=3
    )
    with pytest.raises(GeminiError, match="was not found") as error:
        client.generate([{"text": "hi"}])
    assert "Settings" in str(error.value)
    assert len(request.calls) == 1


def test_list_models_returns_generate_capable_names(monkeypatch):
    import urllib.request

    payload = {
        "models": [
            {
                "name": "models/gemini-flash-latest",
                "supportedGenerationMethods": ["generateContent"],
            },
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/some-tts", "supportedGenerationMethods": ["synthesizeContent"]},
        ]
    }

    class FakeResponse:
        def __init__(self, data):
            self._data = json.dumps(data).encode("utf-8")

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def fake_urlopen(request, timeout):
        assert "v1beta/models" in request.full_url
        return FakeResponse(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = GeminiClient(key_getter=lambda: "k")
    models = client.list_models()
    assert models == ("gemini-flash-latest", "gemini-2.5-flash")


def test_list_models_requires_key():
    client = GeminiClient(key_getter=lambda: None)
    with pytest.raises(GeminiKeyMissing):
        client.list_models()


def test_backoff_doubles_per_attempt_and_caps():
    assert GeminiClient._backoff(503, 0) == 2.0
    assert GeminiClient._backoff(503, 1) == 4.0
    assert GeminiClient._backoff(429, 0) == 8.0
    assert GeminiClient._backoff(429, 2) == 32.0
    assert GeminiClient._backoff(429, 10) == 60.0  # capped


def test_highlights_partial_section_failure_keeps_partial_output():
    calls = []

    def flaky_request(url, payload, timeout):
        calls.append(payload)
        if len(calls) == 2:
            raise http_error(503)  # only the second section fails
        return ok_response(
            '[{"start":"00:00:01","end":"00:00:05","title":"important point",'
            '"score":9,"reason":"assigned action"}]'
        )

    provider = GeminiTextProvider(
        key_getter=lambda: "k",
        request_fn=flaky_request,
        sleep_fn=lambda _s: None,
        min_interval=0,
        chunk_size=10,
    )
    result = provider.extract_highlights("a b c d e f g h i j k l m n o p", "en")
    assert "00:00:01 important point" in result


def test_missing_key_raises_without_request():
    request = RecordingRequest([])
    client = GeminiClient(key_getter=lambda: None, request_fn=request)
    with pytest.raises(GeminiKeyMissing, match="credential manager"):
        client.generate([{"text": "hi"}])
    assert request.calls == []


def test_api_key_is_redacted_from_logs():
    key = "sk-unique-gemini-redaction-key"
    client = GeminiClient(
        key_getter=lambda: key,
        request_fn=RecordingRequest([ok_response("ok")]),
        sleep_fn=lambda _seconds: None,
    )
    client.generate([{"text": "hi"}])
    assert key not in SECRET_REDACTOR.redact(f"error with {key} leaked")
    assert REDACTED in SECRET_REDACTOR.redact(f"error with {key} leaked")


def test_extract_text_handles_blocked_and_empty_responses():
    assert extract_text(ok_response("hello")) == "hello"
    with pytest.raises(GeminiError, match="finishReason"):
        extract_text({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})
    with pytest.raises(GeminiError, match="no candidates"):
        extract_text({})


def test_generate_accumulates_token_usage():
    usage_response = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 34},
    }
    request = RecordingRequest([usage_response, usage_response])
    client = GeminiClient(
        key_getter=lambda: "sk-usage-key",
        request_fn=request,
        sleep_fn=lambda _seconds: None,
        min_interval=0,
    )
    client.generate([{"text": "a"}])
    client.generate([{"text": "b"}])
    assert client.usage.provider == "gemini"
    assert client.usage.requests == 2
    assert client.usage.input_tokens == 240
    assert client.usage.output_tokens == 68
    assert client.usage.images == 0


def test_generate_counts_vision_image_parts():
    request = RecordingRequest([ok_response("described")])
    client = GeminiClient(key_getter=lambda: "sk-usage-key", request_fn=request, min_interval=0)
    parts = [{"text": "prompt"}, inline_data_part("image/png", b"png-bytes")]
    client.generate(parts)
    assert client.usage.images == 1
    assert client.usage.requests == 1


def test_text_provider_uses_injected_prompt_set():
    request = RecordingRequest([ok_response("ok")])
    custom = build_prompt_set({"summary": "CUSTOM {lang} {transcript}"})
    provider = GeminiTextProvider(
        key_getter=lambda: "k",
        request_fn=request,
        sleep_fn=lambda _seconds: None,
        min_interval=0,
        prompts=custom,
    )
    provider.summarize("hello", "tr")
    parts = request.calls[0][1]["contents"][0]["parts"]
    assert parts[0]["text"] == "CUSTOM tr hello"
