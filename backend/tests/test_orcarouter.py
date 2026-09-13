from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from glyph.orcarouter import (
    ENDPOINT,
    OrcaRouterAdapter,
    OrcaRouterError,
    TransportResponse,
    retry_delay,
)

Handler = Callable[[bytes, dict[str, str]], TransportResponse]


def adapter(tmp_path, handler: Handler, model: str = "test/model") -> OrcaRouterAdapter:
    calls: list[tuple[bytes, dict[str, str], float]] = []

    def transport(
        body: bytes, headers: dict[str, str], timeout: float
    ) -> TransportResponse:
        calls.append((body, headers, timeout))
        return handler(body, headers)

    instance = OrcaRouterAdapter(
        api_key="secret-test-key",
        model=model,
        batch_size=2,
        timeout_seconds=10,
        cache_dir=tmp_path,
        transport=transport,
        sleep=lambda _: None,
    )
    instance.calls = calls  # type: ignore[attr-defined]
    return instance


def request_blocks(body: bytes) -> list[dict]:
    return json.loads(json.loads(body)["messages"][-1]["content"])["blocks"]


def success(body: bytes, headers: dict[str, str]) -> TransportResponse:
    items = [
        {"id": block["id"], "translated_text": "翻譯內容", "formula_latex": None}
        for block in request_blocks(body)
    ]
    return chat_response(json.dumps({"items": items}))


def chat_response(content: str, finish_reason: str = "stop") -> TransportResponse:
    envelope = {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}]
    }
    return TransportResponse(200, {}, json.dumps(envelope).encode())


def truncated(body: bytes, headers: dict[str, str]) -> TransportResponse:
    return chat_response('{"items": [', finish_reason="length")


def test_translation_uses_own_key_fixed_endpoint_and_cache(tmp_path):
    ai = adapter(tmp_path, success)
    parsed = ai.parse_translate_and_summarize([(1, "Some prose.")])
    assert parsed.blocks[0].translated_text == "翻譯內容"
    ai.parse_translate_and_summarize([(1, "Some prose.")])
    body, headers, timeout = ai.calls[0]
    assert len(ai.calls) == 1
    assert ENDPOINT == "https://api.orcarouter.ai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer secret-test-key"
    assert json.loads(body)["model"] == "test/model"
    assert json.loads(body)["response_format"] == {"type": "json_object"}
    assert timeout == 10
    cached = "".join(path.read_text() for path in tmp_path.iterdir())
    assert "secret-test-key" not in cached
    other = adapter(tmp_path, success, model="test/model2")
    assert other.batch_cache_path("prompt") != ai.batch_cache_path("prompt")


def test_adapter_requires_key_and_model():
    with pytest.raises(OrcaRouterError, match="Settings"):
        OrcaRouterAdapter(api_key=" ", model="m", batch_size=1, timeout_seconds=1)
    with pytest.raises(OrcaRouterError, match="Settings"):
        OrcaRouterAdapter(api_key="k", model="", batch_size=1, timeout_seconds=1)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 429])
def test_permanent_errors_do_not_retry_or_leak_body(tmp_path, status):
    def handler(body: bytes, headers: dict[str, str]) -> TransportResponse:
        return TransportResponse(status, {}, b"secret-test-key private document")

    ai = adapter(tmp_path, handler)
    with pytest.raises(OrcaRouterError) as error:
        ai.parse_translate_and_summarize([(1, "Prose.")])
    assert len(ai.calls) == 1
    assert f"HTTP {status}" in str(error.value)
    assert "secret-test-key" not in str(error.value)
    assert "private document" not in str(error.value)


def test_transient_retry_is_bounded(tmp_path):
    ai = adapter(tmp_path, lambda body, headers: TransportResponse(503, {}, b""))
    with pytest.raises(OrcaRouterError, match="HTTP 503"):
        ai.parse_translate_and_summarize([(1, "Prose.")])
    assert len(ai.calls) == 3
    assert len({call[0] for call in ai.calls}) == 1


def test_connection_failure_is_retried_then_redacted(tmp_path):
    def handler(body: bytes, headers: dict[str, str]) -> TransportResponse:
        raise OSError("connection reset by secret-test-key")

    ai = adapter(tmp_path, handler)
    with pytest.raises(OrcaRouterError) as error:
        ai.parse_translate_and_summarize([(1, "Prose.")])
    assert len(ai.calls) == 3
    assert "secret-test-key" not in str(error.value)
    assert "connection failed" in str(error.value)


def test_incomplete_coverage_retries_then_rejects(tmp_path):
    ai = adapter(tmp_path, lambda body, headers: chat_response('{"items": []}'))
    with pytest.raises(RuntimeError, match="coverage"):
        ai.parse_translate_and_summarize([(1, "Prose.")])
    assert len(ai.calls) == 2


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"items": [None]}),
        json.dumps(
            {"items": [{"id": [], "translated_text": "中文", "formula_latex": None}]}
        ),
        json.dumps({"items": [{"id": "0", "translated_text": "中文"}]}),
    ],
)
def test_malformed_output_is_retried_safely(tmp_path, content):
    ai = adapter(tmp_path, lambda body, headers: chat_response(content))
    with pytest.raises(RuntimeError):
        ai.parse_translate_and_summarize([(1, "Prose.")])
    assert len(ai.calls) == 2


@pytest.mark.parametrize(
    "envelope",
    [
        b"{}",
        b"[]",
        b"null",
        b'"text"',
        b'{"choices": "text"}',
        b'{"choices": []}',
        b'{"choices": [null]}',
        b'{"choices": ["text"]}',
        b'{"choices": [{"message": null}]}',
        b'{"choices": [{"message": "text"}]}',
        b'{"choices": [{"message": {"content": null}}]}',
        b'{"choices": [{"message": {"content": 5}}]}',
    ],
)
def test_malformed_envelopes_are_reported_as_invalid_json(tmp_path, envelope):
    ai = adapter(tmp_path, lambda body, headers: TransportResponse(200, {}, envelope))
    with pytest.raises(RuntimeError, match="invalid translation JSON"):
        ai.parse_translate_and_summarize([(1, "Prose.")])
    assert len(ai.calls) == 2


def test_429_with_short_retry_after_then_success(tmp_path):
    state = {"calls": 0}

    def handler(body: bytes, headers: dict[str, str]) -> TransportResponse:
        state["calls"] += 1
        if state["calls"] == 1:
            return TransportResponse(429, {"Retry-After": "0"}, b"")
        return success(body, headers)

    ai = adapter(tmp_path, handler)
    assert ai.parse_translate_and_summarize([(1, "Prose.")]).blocks
    assert len(ai.calls) == 2


def test_truncated_output_splits_batch_then_completes(tmp_path):
    sizes: list[int] = []

    def handler(body: bytes, headers: dict[str, str]) -> TransportResponse:
        sizes.append(len(request_blocks(body)))
        return truncated(body, headers) if sizes[-1] > 1 else success(body, headers)

    parsed = adapter(tmp_path, handler).parse_translate_and_summarize(
        [(1, "One.\n\nTwo.")]
    )
    assert sizes == [2, 1, 1]
    assert [block.translated_text for block in parsed.blocks] == [
        "翻譯內容",
        "翻譯內容",
    ]


def test_single_oversized_block_fails_bounded(tmp_path):
    ai = adapter(tmp_path, truncated)
    with pytest.raises(RuntimeError, match="too large"):
        ai.parse_translate_and_summarize([(1, "One.\n\nTwo.")])
    assert len(ai.calls) == 2


@pytest.mark.parametrize(
    ("status", "headers", "attempt", "expected"),
    [
        (500, {}, 0, 1.0),
        (502, {}, 1, 2.0),
        (429, {}, 0, None),
        (429, {"Retry-After": "5"}, 0, 5.0),
        (429, {"Retry-After": "31"}, 0, None),
        (503, {"Retry-After": "garbage"}, 0, None),
        (503, {"Retry-After": "Thu, 01 Jan 1970 00:00:00 GMT"}, 0, None),
        (503, {"Retry-After": "Thu, 01 Jan 1970 00:00:00 -0000"}, 0, None),
        (503, {"Retry-After": "Fri, 01 Jan 2100 00:00:00 -0000"}, 0, None),
        (503, {"Retry-After": "-5"}, 0, None),
        (503, {"retry-after": "3"}, 0, 3.0),
        (418, {}, 0, None),
    ],
)
def test_retry_delay_respects_status_and_retry_after(
    status, headers, attempt, expected
):
    assert retry_delay(TransportResponse(status, headers, b""), attempt) == expected


def test_fatal_error_on_first_batch_stops_later_billable_calls(tmp_path):
    calls: list[bytes] = []

    def transport(
        body: bytes, headers: dict[str, str], timeout: float
    ) -> TransportResponse:
        calls.append(body)
        return TransportResponse(401, {}, b"")

    ai = OrcaRouterAdapter(
        api_key="k",
        model="m",
        batch_size=1,
        timeout_seconds=5,
        cache_dir=tmp_path,
        transport=transport,
        sleep=lambda _: None,
    )
    with pytest.raises(OrcaRouterError, match="HTTP 401"):
        ai.parse_translate_and_summarize([(1, "One.\n\nTwo.\n\nThree.")])
    assert len(calls) == 1
