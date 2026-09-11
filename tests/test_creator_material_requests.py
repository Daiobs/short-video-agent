"""Synthetic evidence through the real Creator -> Provider serialization path."""

import base64
import copy
import io
import json

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services import creator_clone as cc, llm_provider as lp


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))


def sample_set(count=5):
    samples = []
    for i in range(count + 1):
        case = settings.cases_dir / f"case_material_{i}"
        write(case / "enrichment/asr/transcript.json", {"full_text": f"ASR_SENTINEL_{i} 先示范步骤再解释原因。"})
        write(case / "enrichment/ocr/frame_ocr.json", {"full_text": f"OCR_SENTINEL_{i} 画面上的对照文字。"})
        write(case / "enrichment/comments/comment_summary.json", {"top_needs": [f"COMMENT_SENTINEL_{i} 求道具名称"], "status": "success"})
        write(case / "analysis_result.json", {"summary": f"ANALYSIS_SENTINEL_{i} 已有分析观察", "risks": ["仅静态画面"], "visual_analysis": {"subject": f"SUBJECT_{i}"}})
        Image.new("RGB", (40, 40), (i * 20, 10, 30)).save(case / "contact_sheet.jpg")
        samples.append(cc.CloneSample(sample_id=f"sample_material_{i}", case_id=case.name,
                                      title=f"合成素材 {i}", media_type="video", like_count=i,
                                      metric_availability={"like_count": True, "share_count": False}))
    return cc.CloneSampleSet(set_id="clone_material_requests", title="合成素材", samples=samples,
                             selected_sample_ids=[s.sample_id for s in samples[:count]])


def raw_result():
    return {"summary": "保留原摘要", "creator_positioning": {"what_the_creator_sells": "原定位"},
            "creator_clone_spec": {"taste": "基于材料"},
            "transferable_formulas": [{"name": "方法", "beat_structure": ["开始", "FORMULA_END"]}],
            "candidate_ideas": [{"title": "选题", "production_requirements": ["IDEA_END"]}]}


def capture_transport(monkeypatch, errors=()):
    calls = []
    original = httpx.Client

    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        index = len(calls) - 1
        if index < len(errors):
            code = errors[index]
            if code == "invalid":
                return httpx.Response(200, json={"output_text": "not JSON"})
            if code == "timeout":
                raise httpx.ReadTimeout("synthetic", request=request)
            return httpx.Response(code, json={"error": {"message": "synthetic"}})
        return httpx.Response(200, json={"status": "completed", "output_text": json.dumps(raw_result())})

    monkeypatch.setattr(lp.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr(cc, "llm_is_configured", lambda: True)
    monkeypatch.setattr(cc, "get_llm_provider", lambda **kw: lp.OpenAIResponsesProvider(
        api_base="https://synthetic.invalid", api_key="synthetic", model="synthetic", **kw))
    return calls


@pytest.mark.parametrize("count,mode", [(1, "quick"), (2, "deep"), (5, "quick"), (5, "deep")])
def test_formal_requests_carry_selected_text_and_real_images(monkeypatch, count, mode):
    pool = sample_set(count)
    calls = capture_transport(monkeypatch)
    result = cc.distill_creator_clone(pool, pool.selected_sample_ids, distill_mode=mode)["result"]
    assert len(calls) == 1
    content = calls[0]["input"][0]["content"]
    prompt = content[0]["text"]
    images = content[1:]
    assert len(images) == count
    for i in range(count):
        for kind in ("ASR", "OCR", "COMMENT", "ANALYSIS"):
            assert f"{kind}_SENTINEL_{i}" in prompt
        assert f'"sample_id": "sample_material_{i}"' in prompt
        with Image.open(io.BytesIO(base64.b64decode(images[i]["image_url"].split(",", 1)[1]))) as image:
            assert abs(image.getpixel((0, 0))[0] - i * 20) <= 3
    assert f"ASR_SENTINEL_{count}" not in prompt
    assert "localhost" not in str(images)
    assert result["request_materials"]["image_count"] == count
    assert cc.load_creator_clone_result(pool.set_id)["request_materials"] == result["request_materials"]
    assert result["summary"] == raw_result()["summary"]
    assert result["transferable_formulas"] == raw_result()["transferable_formulas"]
    assert "FORMULA_END" in cc.render_creator_clone_markdown(result)


@pytest.mark.parametrize("count", [1, 5])
def test_compact_retry_preserves_materials_and_is_bounded(monkeypatch, count):
    pool = sample_set(count)
    calls = capture_transport(monkeypatch, ("invalid",))
    result = cc.distill_creator_clone(pool, pool.selected_sample_ids)["result"]
    assert len(calls) == 2
    for call in calls:
        assert f"ASR_SENTINEL_{count-1}" in call["input"][0]["content"][0]["text"]
        assert len(call["input"][0]["content"]) == count + 1
    assert result["request_materials"]["successful_attempt"] == 2


@pytest.mark.parametrize("failure", ["timeout", 401, 403, 429])
def test_quick_terminal_failure_does_not_add_calls(monkeypatch, failure):
    pool = sample_set()
    calls = capture_transport(monkeypatch, (failure,))
    with pytest.raises(AppError):
        cc.distill_creator_clone(pool, pool.selected_sample_ids)
    assert len(calls) == 1


def test_batch_owns_its_materials_and_final_is_secondary(monkeypatch):
    pool = sample_set(5)
    calls = capture_transport(monkeypatch)
    payload = cc.batch_distill_creator_clone(pool, pool.selected_sample_ids, batch_size=2)
    assert len(calls) == 4  # Three batches, one existing final Reduce; no new Map calls.
    for index, call in enumerate(calls[:3]):
        prompt = call["input"][0]["content"][0]["text"]
        expected = range(index * 2, min(index * 2 + 2, 5))
        for i in range(5):
            assert (f"ASR_SENTINEL_{i}" in prompt) == (i in expected)
        assert len(call["input"][0]["content"]) == len(expected) + 1
    final = calls[-1]["input"][0]["content"]
    assert len(final) == 1
    assert "本次只提交批次二手摘要" in final[0]["text"]
    assert payload["result"]["request_materials"]["scope"] == "batch_summaries"
    assert payload["result"]["request_materials"]["image_count"] == 0


def test_lite_and_old_map_cache_rebuild_local_inputs(monkeypatch):
    pool = sample_set(5)
    write(settings.creator_clones_dir / pool.set_id / "map_summaries.json", [{"summary": "OLD_CACHE"}])
    calls = capture_transport(monkeypatch)
    cc.distill_creator_clone(pool, pool.selected_sample_ids)
    assert "OLD_CACHE" not in calls[0]["input"][0]["content"][0]["text"]
    selected = pool.samples[:5]
    lite = cc.build_lite_distill_prompt(pool, selected)
    assert all(f"OCR_SENTINEL_{i}" in lite for i in range(5))


def test_retry_records_only_successful_provider_image_scope(monkeypatch):
    pool = sample_set(1)
    captures = []

    class Provider:
        def __init__(self):
            self.supports_images = not captures

        def analyze(self, prompt, images):
            captures.append((prompt, images))
            if len(captures) == 1:
                raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
            return copy.deepcopy(raw_result())

    monkeypatch.setattr(cc, "llm_is_configured", lambda: True)
    monkeypatch.setattr(cc, "get_llm_provider", lambda **kw: Provider())
    result = cc.distill_creator_clone(pool, pool.selected_sample_ids)["result"]
    assert captures[0][1] and not captures[1][1]
    assert "ASR_SENTINEL_0" in captures[1][0]
    assert result["request_materials"]["image_count"] == 0


def test_maximum_batch_text_is_fair_bounded_and_preserves_zero(monkeypatch):
    pool = sample_set(cc.MAX_DISTILL_SAMPLES)
    for i, sample in enumerate(pool.samples[:cc.MAX_DISTILL_SAMPLES]):
        case = settings.cases_dir / sample.case_id
        write(case / "enrichment/asr/transcript.json", {"full_text": f"ASR_SENTINEL_{i} " + "长文本" * 10000})
    calls = capture_transport(monkeypatch)
    cc.distill_creator_clone(pool, pool.selected_sample_ids)
    content = calls[0]["input"][0]["content"]
    prompt = content[0]["text"]
    assert all(f"ASR_SENTINEL_{i}" in prompt for i in range(cc.MAX_DISTILL_SAMPLES))
    assert len(prompt) < 100000
    assert len(content) == 7
    assert '"like_count": 0' in prompt
    assert '"share_count": null' in prompt
    assert '"share_count": false' in prompt
    assert "asr_truncated" in prompt


def test_invalid_case_and_legacy_fallback_cannot_reenter_map(monkeypatch):
    pool = sample_set(2)
    write(settings.cases_dir / "__unavailable_case__/analysis_result.json", {"summary": "UNASSIGNED_SECRET"})
    pool.samples[0].case_id = "../unsafe"
    write(settings.cases_dir / pool.samples[1].case_id / "analysis_result.json",
          {"analysis_mode": "local_fallback", "summary": "FALLBACK_AS_FACT",
           "replication": {"copyable_points": ["FALLBACK_ADVICE"]}})
    calls = capture_transport(monkeypatch)
    cc.distill_creator_clone(pool, pool.selected_sample_ids)
    prompt = calls[0]["input"][0]["content"][0]["text"]
    assert all(marker not in prompt for marker in ("UNASSIGNED_SECRET", "FALLBACK_AS_FACT", "FALLBACK_ADVICE"))
    assert "existing_analysis_fallback" in prompt
