from __future__ import annotations

import pytest

from app.errors import AppError, ErrorCode
from app.services import creator_clone as creator
from app.services.llm_budget import DistillDeadline


def samples(count=5):
    return [creator.CloneSample(sample_id=f"sample_{i}", title=f"Synthetic {i}") for i in range(count)]


@pytest.fixture
def controlled(monkeypatch):
    config = {
        "creator_distill_budget_mode": "auto", "creator_distill_request_timeout_seconds": 180,
        "final_reduce_timeout_seconds": 300, "quick_distill_budget_seconds": 1800,
        "deep_distill_budget_seconds": 3600, "batch_job_budget_seconds": 7200,
        "final_reduce_min_reserve_seconds": 60,
    }
    monkeypatch.setattr(creator, "effective_llm_settings", lambda: config)
    monkeypatch.setattr(creator, "llm_is_configured", lambda: True)
    monkeypatch.setattr(creator, "_sample_duration_seconds", lambda sample: None)
    monkeypatch.setattr(creator, "_prepare_creator_request", lambda prompt, selected, effective: (
        "x" * 8215, {"image_paths": [], "image_bindings": []},
    ))
    return config


def result():
    return {"summary": "Synthetic completed", "creator_positioning": {"what_the_creator_sells": "structure"},
            "creator_clone_spec": {"taste": "evidence"}}


def test_five_sample_request_uses_actual_prompt_plan_and_completes_at_281(monkeypatch, controlled):
    clock = [0.0]
    deadline = DistillDeadline.start(720, clock=lambda: clock[0])
    seen = []
    phases = []

    class Provider:
        def analyze(self, prompt, image_paths):
            clock[0] += 281
            assert seen[0]["deadline"].remaining_seconds() == 64
            return result()

    def factory(**kwargs):
        seen.append(kwargs)
        return Provider()

    monkeypatch.setattr(creator, "get_llm_provider", factory)
    pool = creator.CloneSampleSet(set_id="clone_dynamic_five", samples=samples())
    output = creator.distill_creator_clone(
        pool, [item.sample_id for item in pool.samples], deadline=deadline,
        progress=lambda value, message, phase: phases.append(phase),
    )
    policy = output["execution_plan"]["timeout_policy"]
    assert policy["recommended_batch_timeout_seconds"] == 345
    assert policy["total_request_budget_seconds"] == 720
    assert seen[0]["timeout_seconds"] == 345
    assert deadline.enforce_network is True
    assert len(seen) == 1
    parsed = next(phase for phase in phases if phase.get("current_phase") == "parse_result")
    assert parsed["timeout_seconds"] == 345
    assert parsed["remaining_seconds"] == 439
    assert output["result"]["summary"] == "Synthetic completed"


def test_automatic_plan_grows_and_is_bounded(controlled):
    small = creator.build_distill_execution_plan(samples(), prompt_chars=8215)["timeout_policy"]
    larger = creator.build_distill_execution_plan(samples(15), prompt_chars=18000)["timeout_policy"]
    huge = creator.build_distill_execution_plan(samples(150), prompt_chars=10000000)["timeout_policy"]
    assert small["recommended_batch_timeout_seconds"] == 345
    assert larger["recommended_batch_timeout_seconds"] > 345
    assert huge["recommended_batch_timeout_seconds"] == 1200
    assert huge["recommended_final_reduce_timeout_seconds"] == 2400


def test_manual_request_does_not_pre_reserve_retry(monkeypatch, controlled):
    controlled.update(creator_distill_budget_mode="manual", creator_distill_request_timeout_seconds=120,
                      quick_distill_budget_seconds=120)
    seen = []
    class Provider:
        def analyze(self, prompt, image_paths):
            return result()
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: (seen.append(kwargs) or Provider()))
    pool = creator.CloneSampleSet(set_id="clone_manual", samples=samples())
    output = creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])
    assert 119 < seen[0]["timeout_seconds"] <= 120
    assert output["execution_plan"]["timeout_policy"]["budget_mode"] == "manual"


def test_explicit_task_cap_rejects_insufficient_automatic_plan(monkeypatch, controlled):
    controlled["quick_distill_budget_seconds"] = 240
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kw: pytest.fail("No request authorized by insufficient plan"))
    pool = creator.CloneSampleSet(set_id="clone_short_cap", samples=samples())
    phases = []
    with pytest.raises(AppError, match="自动计划需要 345"):
        creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples], distill_mode="deep",
                                    deadline=DistillDeadline.start(240),
                                    progress=lambda value, message, phase: phases.append(phase))
    failed = phases[-1]
    assert failed["current_phase"] == "budget_planning"
    assert failed["retryable"] is False
    assert "Deep" not in failed["diagnostic"]


def test_auto_exact_cap_allows_clock_jitter_without_extending_deadline(monkeypatch, controlled):
    controlled["quick_distill_budget_seconds"] = 345
    seen = []
    class Provider:
        def analyze(self, prompt, image_paths):
            return result()
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: (seen.append(kwargs) or Provider()))
    pool = creator.CloneSampleSet(set_id="clone_exact_cap", samples=samples())
    output = creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])
    assert 344.95 < seen[0]["timeout_seconds"] <= 345
    assert seen[0]["deadline"].total_budget_seconds <= 345
    assert output["execution_plan"]["timeout_policy"]["budget_limited"] is False


def test_retry_prompt_consumption_is_checked_before_second_provider(monkeypatch, controlled):
    clock = [0.0]
    deadline = DistillDeadline.start(720, clock=lambda: clock[0])
    original_prepare = creator._prepare_creator_request
    prepared = []
    calls = []
    def prepare(*args):
        prepared.append(1)
        if len(prepared) == 2:
            clock[0] = 720
        return original_prepare(*args)
    class Provider:
        def analyze(self, prompt, image_paths):
            raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
    monkeypatch.setattr(creator, "_prepare_creator_request", prepare)
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: (calls.append(1) or Provider()))
    pool = creator.CloneSampleSet(set_id="clone_retry_expired", samples=samples())
    with pytest.raises(AppError) as error:
        creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples], deadline=deadline)
    assert error.value.public_details()["phase"] == "retry_budget"
    assert calls == [1]


def test_default_automatic_total_is_planned_not_fixed_quick_cap(monkeypatch, controlled):
    seen = []
    class Provider:
        def analyze(self, prompt, image_paths):
            return result()
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: (seen.append(kwargs) or Provider()))
    pool = creator.CloneSampleSet(set_id="clone_auto_total", samples=samples())
    output = creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])
    assert output["execution_plan"]["timeout_policy"]["total_request_budget_seconds"] == 720
    assert output["execution_plan"]["timeout_policy"]["task_cap_seconds"] == 1800
    assert seen[0]["timeout_seconds"] == 345


def test_batch_budget_exhaustion_preserves_existing_report(monkeypatch, controlled):
    controlled["batch_job_budget_seconds"] = 40
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kw: pytest.fail("Reserved final budget cannot fit"))
    pool = creator.CloneSampleSet(set_id="clone_preserve_old", samples=samples())
    output_dir = creator.creator_clone_dir(pool.set_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    old = output_dir / "creator_clone_result.json"
    old.write_text('{"summary":"old report"}', encoding="utf-8")
    before = old.read_bytes()
    output = creator.batch_distill_creator_clone(pool, [s.sample_id for s in pool.samples], batch_size=2)
    assert output["batch_distill"]["job_status"] == "budget_exhausted"
    assert old.read_bytes() == before
    assert (output_dir / "batch_distill" / "manifest.json").is_file()


@pytest.mark.parametrize("error", [ErrorCode.LLM_GATEWAY_TIMEOUT, ErrorCode.LLM_AUTH_FAILED,
                                   ErrorCode.LLM_RATE_LIMITED, ErrorCode.LLM_QUOTA_EXCEEDED])
def test_quick_stop_errors_never_resend(monkeypatch, controlled, error):
    calls = []
    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append(1)
            raise AppError(error)
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Provider())
    pool = creator.CloneSampleSet(set_id="clone_stop", samples=samples())
    with pytest.raises(AppError):
        creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])
    assert calls == [1]


def test_batches_share_deadline_and_reserve_final(monkeypatch, controlled):
    clock = [0.0]
    deadline = DistillDeadline.start(1800, clock=lambda: clock[0])
    seen = []
    class Provider:
        def analyze(self, prompt, image_paths):
            clock[0] += 100
            return result()
    def factory(**kwargs):
        seen.append((clock[0], kwargs["timeout_seconds"], kwargs["deadline"].deadline_monotonic))
        return Provider()
    monkeypatch.setattr(creator, "get_llm_provider", factory)
    pool = creator.CloneSampleSet(set_id="clone_dynamic_batch", samples=samples(4))
    output = creator.batch_distill_creator_clone(pool, [s.sample_id for s in pool.samples], batch_size=2, deadline=deadline)
    assert len(seen) == 3
    assert [row[0] for row in seen] == [0, 100, 200]
    assert all(row[2] <= 1800 for row in seen)
    assert output["batch_distill"]["final_reduce_min_reserve_seconds"] >= 450
    assert output["execution_plan"]["timeout_policy"]["effective_request_timeout_seconds"] == seen[-1][1]


def test_route_keeps_actual_plan_and_budget_mode(controlled):
    from app.routes.jobs import _distill_phase_payload
    plan = creator.build_distill_execution_plan(samples(), prompt_chars=8215, budget_mode="manual")
    phase = _distill_phase_payload({"execution_plan": plan, "timeout_seconds": 180,
                                   "total_budget_seconds": 300, "deadline_at": "test"})
    assert phase["budget_mode"] == "manual"
    assert phase["execution_plan"] == plan
    assert phase["deadline_at"] == "test"
