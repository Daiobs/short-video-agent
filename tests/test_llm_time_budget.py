from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.config import settings
from app.errors import AppError, ErrorCode
from app.routes.jobs import _distill_fallback_message, _distill_phase_payload
from app.services.creator_clone import (
    CloneSample,
    CloneSampleSet,
    batch_distill_creator_clone,
    distill_creator_clone,
)
from app.services.llm_budget import DistillDeadline
from app.services.llm_provider import OpenAICompatibleProvider, get_llm_provider


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeResponse:
    def __init__(self, status_code: int, *, text: str = "", payload=None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.content = text.encode()

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        if self._payload is None:
            return {}
        return self._payload


def success_response() -> FakeResponse:
    return FakeResponse(
        200,
        payload={"choices": [{"message": {"content": '{"ok": true}'}}]},
    )


def test_gateway_timeout_fallback_message_is_actionable() -> None:
    message = _distill_fallback_message(
        AppError(ErrorCode.LLM_GATEWAY_TIMEOUT, "大模型网关请求超时。"),
        distill_mode="quick",
    )

    assert "网关请求超时" in message
    assert "Quick" in message
    assert "Deep" in message
    assert "暂不可用" not in message


def test_deep_gateway_timeout_fallback_message_does_not_claim_another_retry() -> None:
    message = _distill_fallback_message(
        AppError(ErrorCode.LLM_GATEWAY_TIMEOUT, "大模型网关请求超时。"),
        distill_mode="deep",
    )

    assert "Deep" in message
    assert "仍然超时" in message
    assert "重试" not in message


def test_global_and_creator_request_timeout_defaults_are_separate() -> None:
    assert settings.llm_timeout_seconds == 90
    assert settings.llm_creator_distill_request_timeout_seconds == 180


def test_default_provider_uses_global_request_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.llm_provider.effective_llm_settings",
        lambda: {
            "provider": "openai_compatible",
            "api_base": "https://gateway.example/v1",
            "api_key": "sk-test",
            "model": "test-model",
            "timeout_seconds": 90,
            "temperature": 0.2,
            "max_output_tokens": 1200,
        },
    )

    provider = get_llm_provider()

    assert provider.timeout_seconds == 90


def install_http_sequence(monkeypatch, responses, *, clock: FakeClock | None = None, advance: float = 0):
    calls: list[dict] = []
    client_timeouts: list[float] = []
    queue = list(responses)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            client_timeouts.append(float(kwargs.get("timeout") or 0))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            calls.append({"url": url, "headers": headers, "json": dict(json or {})})
            if clock and advance:
                clock.advance(advance)
            value = queue.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    return calls, client_timeouts


def make_provider(*, deadline: DistillDeadline | None = None) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_base="https://gateway.example/v1",
        api_key="sk-secret-never-return",
        model="test-model",
        timeout_seconds=60,
        deadline=deadline,
    )


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (401, "unauthorized", ErrorCode.LLM_AUTH_FAILED),
        (403, "forbidden", ErrorCode.LLM_AUTH_FAILED),
        (429, "rate limit", ErrorCode.LLM_RATE_LIMITED),
        (429, "insufficient_quota", ErrorCode.LLM_QUOTA_EXCEEDED),
        (502, "bad gateway", ErrorCode.LLM_UPSTREAM_UNAVAILABLE),
        (503, "unavailable", ErrorCode.LLM_UPSTREAM_UNAVAILABLE),
        (504, "gateway timeout", ErrorCode.LLM_GATEWAY_TIMEOUT),
    ],
)
def test_llm_http_failures_are_stable_and_do_not_retry(monkeypatch, status_code, body, expected) -> None:
    calls, _ = install_http_sequence(monkeypatch, [FakeResponse(status_code, text=body)])

    with pytest.raises(AppError) as raised:
        make_provider().analyze("private prompt", [])

    assert raised.value.code == expected
    assert len(calls) == 1
    diagnostics = raised.value.public_details()
    assert diagnostics["status_code"] == status_code
    assert diagnostics["retryable"] is (expected in {ErrorCode.LLM_UPSTREAM_UNAVAILABLE, ErrorCode.LLM_GATEWAY_TIMEOUT})
    serialized = str(raised.value.as_dict())
    assert "sk-secret-never-return" not in serialized
    assert "private prompt" not in serialized
    assert "Authorization" not in serialized
    assert body not in serialized


def test_transport_timeout_is_gateway_timeout(monkeypatch) -> None:
    request = httpx.Request("POST", "https://gateway.example/v1/chat/completions")
    calls, _ = install_http_sequence(monkeypatch, [httpx.ReadTimeout("slow", request=request)])

    with pytest.raises(AppError) as raised:
        make_provider().analyze("prompt", [])

    assert raised.value.code == ErrorCode.LLM_GATEWAY_TIMEOUT
    assert raised.value.public_details()["retryable"] is True
    assert len(calls) == 1


def test_invalid_json_is_response_invalid(monkeypatch) -> None:
    calls, _ = install_http_sequence(
        monkeypatch,
        [FakeResponse(200, payload=ValueError("not json"))],
    )

    with pytest.raises(AppError) as raised:
        make_provider().analyze("prompt", [])

    assert raised.value.code == ErrorCode.LLM_RESPONSE_INVALID
    assert len(calls) == 1


def test_response_format_fallback_is_explicit_and_shares_deadline(monkeypatch) -> None:
    clock = FakeClock()
    deadline = DistillDeadline.start(
        20,
        clock=clock,
        wall_now=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    calls, timeouts = install_http_sequence(
        monkeypatch,
        [
            FakeResponse(400, text="response_format is unsupported"),
            success_response(),
        ],
        clock=clock,
        advance=3,
    )
    provider = make_provider(deadline=deadline)

    assert provider.analyze("prompt", []) == {"ok": True}
    assert len(calls) == 2
    assert "response_format" in calls[0]["json"]
    assert "response_format" not in calls[1]["json"]
    assert timeouts[0] <= 20
    assert timeouts[1] <= 17
    assert provider.public_diagnostics() == {
        "provider": "openai_compatible",
        "http_attempt_index": 2,
        "http_attempt_count": 2,
        "response_format_fallback_used": True,
    }


def test_arbitrary_400_does_not_trigger_response_format_fallback(monkeypatch) -> None:
    calls, _ = install_http_sequence(
        monkeypatch,
        [FakeResponse(400, text="invalid model")],
    )

    with pytest.raises(AppError) as raised:
        make_provider().analyze("prompt", [])

    assert raised.value.code == ErrorCode.LLM_REQUEST_FAILED
    assert len(calls) == 1


def _sample_set(set_id: str = "clone_budget_test", count: int = 2) -> CloneSampleSet:
    return CloneSampleSet(
        set_id=set_id,
        title="预算测试",
        samples=[
            CloneSample(sample_id=f"sample_{index}", title=f"样本 {index}", like_count=10 - index)
            for index in range(count)
        ],
    )


def _strategy_result(summary: str = "完成") -> dict:
    return {
        "summary": summary,
        "creator_positioning": {"what_the_creator_sells": "稳定结构"},
        "creator_clone_spec": {"taste": "证据优先"},
    }


@pytest.mark.parametrize(
    "error_code",
    [
        ErrorCode.LLM_RATE_LIMITED,
        ErrorCode.LLM_AUTH_FAILED,
        ErrorCode.LLM_QUOTA_EXCEEDED,
    ],
)
def test_non_retryable_distill_failure_makes_one_logical_request(monkeypatch, error_code) -> None:
    provider_calls: list[int] = []

    class Provider:
        def analyze(self, prompt, image_paths):
            provider_calls.append(1)
            raise AppError(error_code, details={"retryable": False, "status_code": 429})

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", lambda **kwargs: Provider())
    sample_set = _sample_set(set_id=f"clone_{error_code.lower()}")

    with pytest.raises(AppError) as raised:
        distill_creator_clone(sample_set, [sample.sample_id for sample in sample_set.samples])

    assert raised.value.code == error_code
    assert provider_calls == [1]


def test_invalid_response_can_use_one_compact_retry(monkeypatch) -> None:
    calls: list[int] = []

    class Provider:
        def __init__(self, index: int) -> None:
            self.index = index

        def analyze(self, prompt, image_paths):
            calls.append(self.index)
            if self.index == 1:
                raise AppError(ErrorCode.LLM_RESPONSE_INVALID, details={"retryable": True})
            return _strategy_result("精简重试成功")

    def provider_factory(**kwargs):
        return Provider(len(calls) + 1)

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", provider_factory)
    sample_set = _sample_set("clone_invalid_retry")

    result = distill_creator_clone(sample_set, [sample.sample_id for sample in sample_set.samples])

    assert result["result"]["summary"] == "精简重试成功"
    assert calls == [1, 2]
    assert result["execution_plan"]["timeout_policy"]["max_external_attempts"] == 2
    assert result["execution_plan"]["timeout_policy"]["max_http_attempts_per_logical_request"] == 2
    assert result["execution_plan"]["timeout_policy"]["max_total_external_http_requests"] == 4
    assert result["execution_plan"]["timeout_policy"]["distill_mode"] == "quick"
    assert result["execution_plan"]["timeout_policy"]["timeout_retry_enabled"] is False


def test_quick_timeout_makes_one_logical_request(monkeypatch) -> None:
    calls: list[int] = []
    provider_timeouts: list[int] = []
    progress_events: list[dict] = []

    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append(1)
            raise AppError(ErrorCode.LLM_GATEWAY_TIMEOUT, details={"retryable": True})

    def provider_factory(**kwargs):
        provider_timeouts.append(int(kwargs["timeout_seconds"]))
        return Provider()

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", provider_factory)
    sample_set = _sample_set("clone_quick_timeout")

    with pytest.raises(AppError) as raised:
        distill_creator_clone(
            sample_set,
            [sample.sample_id for sample in sample_set.samples],
            distill_mode="quick",
            progress=lambda value, message, phase=None: progress_events.append(phase or {}),
        )

    assert raised.value.code == ErrorCode.LLM_GATEWAY_TIMEOUT
    assert calls == [1]
    assert provider_timeouts == [180]
    failed = next(item for item in progress_events if item.get("current_phase") == "llm_failed")
    assert failed["retryable"] is False
    assert failed["execution_plan"]["timeout_policy"]["total_request_budget_seconds"] == 240
    assert failed["execution_plan"]["timeout_policy"]["timeout_retry_enabled"] is False


def test_deep_timeout_can_use_one_compact_retry(monkeypatch) -> None:
    calls: list[int] = []
    provider_timeouts: list[int] = []

    class Provider:
        def __init__(self, index: int) -> None:
            self.index = index

        def analyze(self, prompt, image_paths):
            calls.append(self.index)
            if self.index == 1:
                raise AppError(ErrorCode.LLM_GATEWAY_TIMEOUT, details={"retryable": True})
            return _strategy_result("Deep timeout 重试成功")

    def provider_factory(**kwargs):
        provider_timeouts.append(int(kwargs["timeout_seconds"]))
        return Provider(len(provider_timeouts))

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", provider_factory)
    sample_set = _sample_set("clone_deep_timeout")

    result = distill_creator_clone(
        sample_set,
        [sample.sample_id for sample in sample_set.samples],
        distill_mode="deep",
    )

    assert result["result"]["summary"] == "Deep timeout 重试成功"
    assert calls == [1, 2]
    assert provider_timeouts == [180, 180]
    policy = result["execution_plan"]["timeout_policy"]
    assert policy["total_request_budget_seconds"] == 600
    assert policy["timeout_retry_enabled"] is True


def test_creator_distill_uses_creator_request_timeout(monkeypatch) -> None:
    provider_timeouts: list[int] = []

    class Provider:
        def analyze(self, prompt, image_paths):
            return _strategy_result("Creator timeout 已隔离")

    def provider_factory(**kwargs):
        provider_timeouts.append(int(kwargs["timeout_seconds"]))
        return Provider()

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", provider_factory)
    sample_set = _sample_set("clone_creator_timeout")

    result = distill_creator_clone(
        sample_set,
        [sample.sample_id for sample in sample_set.samples],
    )

    assert result["result"]["summary"] == "Creator timeout 已隔离"
    assert provider_timeouts == [180]
    assert result["execution_plan"]["timeout_policy"]["configured_batch_timeout_seconds"] == 180


def test_timeout_without_minimum_remaining_budget_does_not_retry(monkeypatch) -> None:
    clock = FakeClock()
    deadline = DistillDeadline.start(
        20,
        clock=clock,
        wall_now=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    calls: list[int] = []

    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append(1)
            clock.advance(20)
            raise AppError(ErrorCode.LLM_GATEWAY_TIMEOUT, details={"retryable": True})

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", lambda **kwargs: Provider())
    sample_set = _sample_set("clone_timeout_exhausted")

    with pytest.raises(AppError) as raised:
        distill_creator_clone(
            sample_set,
            [sample.sample_id for sample in sample_set.samples],
            deadline=deadline,
        )

    assert raised.value.code == ErrorCode.LLM_GATEWAY_TIMEOUT
    assert calls == [1]
    assert deadline.elapsed_seconds() == 20


def test_batch_budget_stops_new_requests_and_preserves_results(monkeypatch) -> None:
    clock = FakeClock()
    deadline = DistillDeadline.start(
        40,
        clock=clock,
        wall_now=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    calls: list[float] = []

    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append(clock())
            clock.advance(12)
            return _strategy_result(f"批次 {len(calls)}")

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", lambda **kwargs: Provider())
    monkeypatch.setattr(
        "app.services.creator_clone.effective_llm_settings",
        lambda: {
            "timeout_seconds": 30,
            "final_reduce_timeout_seconds": 30,
            "batch_job_budget_seconds": 40,
            "final_reduce_min_reserve_seconds": 10,
            "max_output_tokens": 1200,
            "final_reduce_max_output_tokens": 4000,
        },
    )
    sample_set = _sample_set("clone_batch_exhausted", count=4)

    result = batch_distill_creator_clone(
        sample_set,
        [sample.sample_id for sample in sample_set.samples],
        batch_size=1,
        max_samples=10,
        deadline=deadline,
    )

    manifest = result["batch_distill"]
    assert len(calls) < 5
    assert manifest["job_status"] == "budget_exhausted"
    assert manifest["successful_batch_count"] >= 1
    assert any(item["status"] == "budget_exhausted" for item in manifest["batches"])
    assert manifest["final_reduce_min_reserve_seconds"] == 10
    assert deadline.elapsed_seconds() <= 40 + 12


def test_batch_budget_reserves_final_reduce(monkeypatch) -> None:
    clock = FakeClock()
    deadline = DistillDeadline.start(
        60,
        clock=clock,
        wall_now=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    observed_deadlines: list[float] = []

    class Provider:
        def analyze(self, prompt, image_paths):
            clock.advance(1)
            return _strategy_result()

    def provider_factory(**kwargs):
        observed_deadlines.append(float(kwargs["deadline"].total_budget_seconds))
        return Provider()

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", provider_factory)
    monkeypatch.setattr(
        "app.services.creator_clone.effective_llm_settings",
        lambda: {
            "timeout_seconds": 20,
            "final_reduce_timeout_seconds": 30,
            "batch_job_budget_seconds": 60,
            "final_reduce_min_reserve_seconds": 15,
            "max_output_tokens": 1200,
            "final_reduce_max_output_tokens": 4000,
        },
    )
    sample_set = _sample_set("clone_batch_reserve", count=3)

    result = batch_distill_creator_clone(
        sample_set,
        [sample.sample_id for sample in sample_set.samples],
        batch_size=1,
        max_samples=10,
        deadline=deadline,
    )

    assert result["batch_distill"]["job_status"] == "completed"
    assert len(observed_deadlines) == 4
    assert observed_deadlines[-1] >= 15
    assert result["batch_distill"]["final"]["status"] == "success"


def test_progress_dto_is_bounded_and_secret_free() -> None:
    payload = _distill_phase_payload(
        {
            "status": "failed",
            "failure_class": ErrorCode.LLM_RATE_LIMITED,
            "retryable": False,
            "http_attempt_index": 1,
            "http_attempt_count": 1,
            "response_format_fallback_used": False,
            "api_key": "sk-secret",
            "authorization": "Bearer secret",
            "prompt": "private prompt",
            "gateway_response": "private response",
        }
    )

    assert payload["failure_class"] == ErrorCode.LLM_RATE_LIMITED
    assert payload["retryable"] is False
    assert payload["http_attempt_count"] == 1
    serialized = str(payload)
    assert "sk-secret" not in serialized
    assert "Bearer secret" not in serialized
    assert "private prompt" not in serialized
    assert "private response" not in serialized
