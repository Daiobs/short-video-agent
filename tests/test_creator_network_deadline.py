"""No external traffic: Creator cancellation and long-read budgets."""
import asyncio
import json

import httpx
import pytest

from app.errors import AppError, ErrorCode
from app.services import llm_provider
from app.services.llm_budget import DistillDeadline


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    clients = []

    def factory(**kwargs):
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return clients


def provider(deadline, timeout=345):
    return llm_provider.OpenAIResponsesProvider(
        api_base="https://mock.invalid", api_key="synthetic", model="mock-model",
        timeout_seconds=timeout, deadline=deadline,
    )


def test_281_second_response_succeeds_with_short_connect_and_long_read(monkeypatch):
    now = [0.0]
    deadline = DistillDeadline.start(345, clock=lambda: now[0])
    deadline.enforce_network = True
    captured = []

    async def handler(request):
        captured.append(request.extensions["timeout"])
        now[0] += 281
        return httpx.Response(200, json={"output_text": '{"ok": true}'})

    clients = install_transport(monkeypatch, handler)
    assert provider(deadline).analyze("synthetic evidence", []) == {"ok": True}
    assert len(captured) == 1
    assert captured[0] == {"connect": 10, "read": 345, "write": 30, "pool": 10}
    assert deadline.remaining_seconds() == 64
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_local_deadline_cancels_and_closes_pending_io(monkeypatch, phase):
    closed = []
    calls = []

    class PendingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                await asyncio.Event().wait()
                yield b"never"
            finally:
                closed.append("body_cancelled")

        async def aclose(self):
            closed.append("body_closed")

    async def handler(request):
        calls.append(request)
        if phase == "headers":
            try:
                await asyncio.Event().wait()
            finally:
                closed.append("headers_cancelled")
        return httpx.Response(200, stream=PendingBody())

    clients = install_transport(monkeypatch, handler)
    deadline = DistillDeadline.start(0.2)
    deadline.enforce_network = True
    with pytest.raises(AppError) as caught:
        provider(deadline, 0.1).analyze("synthetic", [])
    assert caught.value.code == ErrorCode.LLM_GATEWAY_TIMEOUT
    assert len(calls) == 1
    assert f"{phase}_cancelled" in closed
    assert all(client.is_closed for client in clients)
    if phase == "body":
        assert "body_closed" in closed


def test_child_preserves_network_bound_and_parent_remaining():
    now = [0.0]
    root = DistillDeadline.start(400, clock=lambda: now[0])
    root.enforce_network = True
    now[0] = 300
    child = root.child(345)
    assert child.enforce_network
    assert child.remaining_seconds() == 100
    now[0] = 401
    with pytest.raises(AppError):
        child.require_remaining()


@pytest.mark.parametrize("status,body,code", [
    (401, {}, ErrorCode.LLM_AUTH_FAILED), (403, {}, ErrorCode.LLM_AUTH_FAILED),
    (429, {}, ErrorCode.LLM_RATE_LIMITED),
    (402, {"error": {"message": "insufficient_quota"}}, ErrorCode.LLM_QUOTA_EXCEEDED),
])
def test_creator_async_transport_keeps_error_classification(monkeypatch, status, body, code):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    install_transport(monkeypatch, handler)
    deadline = DistillDeadline.start(345)
    deadline.enforce_network = True
    with pytest.raises(AppError) as caught:
        provider(deadline).analyze("synthetic", [])
    assert caught.value.code == code
    assert len(calls) == 1


def test_protocol_format_fallback_uses_remaining_creator_deadline(monkeypatch):
    now = [0.0]
    deadline = DistillDeadline.start(345, clock=lambda: now[0])
    deadline.enforce_network = True
    captured = []

    async def handler(request):
        captured.append((request.extensions["timeout"], json.loads(request.content)))
        now[0] += 10
        if len(captured) == 1:
            return httpx.Response(400, text="response_format is unsupported")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})

    install_transport(monkeypatch, handler)
    client = llm_provider.OpenAICompatibleProvider(
        api_base="https://mock.invalid", api_key="synthetic", model="mock-model",
        timeout_seconds=345, deadline=deadline,
    )
    assert client.analyze("synthetic", []) == {"ok": True}
    assert [call[0]["read"] for call in captured] == [345, 335]
    assert "response_format" not in captured[1][1]
