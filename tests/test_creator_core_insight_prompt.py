import pytest

from app.services import creator_clone as creator


@pytest.mark.parametrize("profile,title", [
    ("beauty_cos", "同角色的两套造型"),
    ("tutorial", "用纸条演示折角步骤"),
    ("auto", "标题信息有限的混合素材"),
])
def test_core_guidance_reaches_provider_and_existing_report_fields(monkeypatch, profile, title):
    sample_set = creator.CloneSampleSet(
        set_id="clone_core_prompt_test", title=title, content_profile=profile,
        samples=[creator.CloneSample(sample_id=f"sample_{i}", title=f"{title} {i}") for i in range(5)],
    )
    calls = []

    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append((prompt, image_paths))
            return {
                "summary": "合成摘要：固定问题，以两种做法对照，下一条仅改变一个条件。",
                "creator_positioning": {"what_the_creator_sells": "以对照呈现差异的账号"},
                "creator_clone_spec": {"taste": "具体对照"},
            }

    monkeypatch.setattr(creator, "llm_is_configured", lambda: True)
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Provider())
    result = creator.distill_creator_clone(sample_set, [s.sample_id for s in sample_set.samples])
    assert len(calls) == 1
    prompt, images = calls[0]
    assert "样本摘要：" in prompt  # Five samples still use the existing micro path.
    assert "定位标题概括账号，摘要展开方法" in prompt
    assert "没有提供画面不声称亲眼看过" in prompt
    assert "不为凑数量补通用模板" in prompt
    assert images == []  # Prompt-only change, not new visual input wiring.
    assert result["result"]["summary"].startswith("合成摘要：")
    assert result["result"]["creator_positioning"]["what_the_creator_sells"] == "以对照呈现差异的账号"
    assert result["result"]["creator_clone_strategy"]["positioning"]
    assert result["result"]["creator_report_view_model"]

    maps = creator.build_sample_map_summaries(sample_set.samples)
    prompts = [
        creator.build_distill_prompt(sample_set, sample_set.samples),
        creator.build_lite_distill_prompt(sample_set, sample_set.samples),
        creator.build_reduce_distill_prompt(sample_set, sample_set.samples, maps),
        creator.build_final_creator_clone_reduce_prompt(sample_set, sample_set.samples, []),
    ]
    for text in prompts:
        assert text.count("核心判断表达要求") == 1
        assert "新创意明确是建议" in text
        assert "creator_clone_strategy" in text
