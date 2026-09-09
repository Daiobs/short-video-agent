"""Synthetic C-shaped data; no real creator text, IDs or responses."""
import copy

from app.services.creator_clone import CloneSample, CloneSampleSet


def backend_fixture():
    samples = [CloneSample(f"sample_demo_{n}", case_id=f"case_demo_{n}",
                           aweme_id=f"700000000000000000{n}", title=f"Synthetic work {n}",
                           has_comments=True, has_asr=True, has_ocr=True, has_frames=True,
                           has_video=True, selected=True) for n in range(5)]
    report = {
        "summary": "A controlled comparison of costume and scene changes.",
        "creator_positioning": {"audience_assumption": "A hypothesis, not observed audience data."},
        "expression_patterns": {
            "opening_hooks": [{"pattern": "A close view followed by an object reveal.", "evidence": [samples[0].sample_id]}],
            "shot_types": [{"pattern": "Two visible frame sizes.", "evidence": [samples[1].case_id]}],
            "visual_style": [{"pattern": "A plain background visible in the supplied image.", "evidence": [samples[0].aweme_id]}],
            "subtitle_voice": [{"pattern": "OCR and ASR differ; keep their sources separate.",
                                "evidence": [samples[0].sample_id, "sample_demo_typo"], "evidence_level": "high"}],
        },
        "transferable_formulas": [{"name": "One-variable comparison", "beat_structure": ["Reveal", "Contrast"],
            "supporting_samples": [{"sample_id": samples[0].sample_id, "title": "Model invented title", "metric": "share_count", "metric_value": 30}],
            "when_to_use": "A proposed experiment, not a causal explanation."}],
        "candidate_ideas": [{"title": "A new contrast", "evidence": [samples[2].sample_id]}],
        "focused_analysis": [{"observation": "Visible object contrast", "interpretation": "May aid recognition",
                              "transfer": "Test one object change", "uncertainty": "No retention data",
                              "evidence": [samples[0].sample_id]}],
        "request_evidence": {"version": 1, "source": "actual_request", "final_attempt": True, "attempt": 1,
            "samples": [{"sample_id": s.sample_id, "image_orders": [n + 1] if n < 2 else [],
                         "materials": [{"kind": "ocr", "chars": 25}] + ([{"kind": "asr", "chars": 12}] if n in (0, 4) else [])}
                        for n, s in enumerate(samples)]},
    }
    return copy.deepcopy(report), CloneSampleSet("clone_backend", samples=samples, selected_sample_ids=[s.sample_id for s in samples]), samples
