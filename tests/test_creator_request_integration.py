"""Isolated Creator request integration: no real gateways or user archives."""
import json

import pytest
import httpx
from PIL import Image

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services import creator_clone as creator
from app.services import llm_provider


def visual_pool():
    samples = []
    for index in range(3):
        sample = creator.CloneSample(
            sample_id=f"sample_visual_{index}", case_id=f"case_visual_{index}",
            title=f"Synthetic visual {index}", content_category="beauty_cos",
            understanding_level="partial", has_frames=True,
        )
        directory = settings.cases_dir / sample.case_id
        directory.mkdir(parents=True)
        Image.new("RGB", (48, 48), (index * 70, 80, 100)).save(directory / "contact_sheet.jpg")
        (directory / "analysis_input.json").write_text(json.dumps({
            "analysis_enrichment": {
                "asr": {"full_text": f"spoken_marker_{index}"},
                "ocr": {"frame_text": f"screen_marker_{index}"},
                "comments": {"status": "success", "total_comments": 9},
            },
        }))
        samples.append(sample)
    return creator.CloneSampleSet("clone_request_integration", samples=samples)


def configure(monkeypatch):
    original = creator.effective_llm_settings()
    monkeypatch.setattr(creator, "effective_llm_settings", lambda: {
        **original, "provider": "openai_responses", "max_keyframes": 2,
    })
    monkeypatch.setattr(creator, "llm_is_configured", lambda: True)


@pytest.mark.parametrize("retry", [False, True])
def test_actual_provider_images_and_final_request_survive_save_reload(monkeypatch, retry):
    pool = visual_pool()
    configure(monkeypatch)
    calls = []

    class Provider:
        def analyze(self, prompt, images):
            calls.append((prompt, images))
            assert len(images) == 2
            expected = ["case_visual_1", "case_visual_2"] if retry and len(calls) == 2 else ["case_visual_0", "case_visual_1"]
            assert [p.parent.name for p in images] == expected
            for index in range(3):
                assert f"spoken_marker_{index}" in prompt
                assert f"screen_marker_{index}" in prompt
            if retry and len(calls) == 1:
                # Material disappears before retry: do not inherit the failed
                # attempt's image manifest as successful input.
                images[0].unlink()
                raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
            return {"summary": "Synthetic concrete observation", "creator_positioning": {
                "what_the_creator_sells": "Synthetic positioning"}}

    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Provider())
    result = creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])["result"]
    assert len(calls) == (2 if retry else 1)
    recorded = result["request_evidence"]
    assert recorded["attempt"] == len(calls)
    assert recorded["final_attempt"] is True
    assert recorded["degraded"] is retry
    rows = {s["sample_id"]: s for s in recorded["samples"]}
    assert len(rows) == 3
    assert rows["sample_visual_0"]["image_orders"] == ([] if retry else [1])
    assert rows["sample_visual_2"]["image_orders"] == ([2] if retry else [])
    for row in rows.values():
        assert {m["kind"] for m in row["materials"]} == {"asr", "ocr"}
    assert "spoken_marker" not in json.dumps(recorded)
    saved = json.loads((settings.creator_clones_dir / pool.set_id / "creator_clone_result.json").read_text())
    assert saved["request_evidence"] == recorded
    assert saved["report_provenance"]["fields"]["summary"] == "model"


def test_failed_generation_keeps_previous_report_and_does_not_claim_prepared_input(monkeypatch):
    pool = visual_pool()
    configure(monkeypatch)
    directory = creator.creator_clone_dir(pool.set_id)
    saved = directory / "creator_clone_result.json"
    previous = b'{"summary":"previous valid report"}'
    saved.write_bytes(previous)

    class Provider:
        def analyze(self, prompt, images):
            assert len(images) == 2
            raise AppError(ErrorCode.LLM_AUTH_FAILED)

    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Provider())
    with pytest.raises(AppError):
        creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])
    assert saved.read_bytes() == previous


def test_responses_transport_body_contains_bound_images_and_evidence(monkeypatch):
    pool = visual_pool()
    configure(monkeypatch)
    effective = {**creator.effective_llm_settings(), "api_base": "https://synthetic.invalid/v1",
                 "api_key": "test-only-key", "model": "synthetic-vision"}
    monkeypatch.setattr(llm_provider, "effective_llm_settings", lambda: effective)
    captured = []

    def post(client, endpoint, **kwargs):
        body = kwargs["json"]
        captured.append(body)
        content = body["input"][0]["content"]
        prompt = next(row["text"] for row in content if row["type"] == "input_text")
        images = [row for row in content if row["type"] == "input_image"]
        assert len(images) == 2
        assert all(row["image_url"].startswith("data:image/jpeg;base64,") for row in images)
        assert '"sample_id": "sample_visual_0", "image_order": 1' in prompt
        assert '"sample_id": "sample_visual_1", "image_order": 2' in prompt
        for index in range(3):
            assert f"spoken_marker_{index}" in prompt and f"screen_marker_{index}" in prompt
        return httpx.Response(200, json={"output": [{"type": "message", "content": [{
            "type": "output_text", "text": json.dumps({"summary": "Synthetic transport response",
                "creator_positioning": {"what_the_creator_sells": "Synthetic visual structure"}}),
        }]}]}, request=httpx.Request("POST", endpoint))

    monkeypatch.setattr(httpx.Client, "post", post)
    result = creator.distill_creator_clone(pool, [s.sample_id for s in pool.samples])["result"]
    assert len(captured) == 1
    assert result["request_evidence"]["final_attempt"] is True
    assert sum(bool(row["image_orders"]) for row in result["request_evidence"]["samples"]) == 2
