"""Exact Creator reference resolution; identities come only from server samples."""
from __future__ import annotations

import copy
import json
import re


_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")
_NARRATIVE_ID = re.compile(r"(?<![A-Za-z0-9_])(?:sample_|case_)[A-Za-z0-9_-]+(?![A-Za-z0-9_])")
_ROOTS = {"summary", "creator_positioning", "thinking_patterns", "topic_buckets",
          "expression_patterns", "transferable_formulas", "creator_clone_spec",
          "candidate_ideas", "next_actions", "focused_analysis", "content_groups",
          "creator_clone_strategy", "performance_segments"}
_REF_LISTS = {"evidence", "sample_ids", "supporting_samples", "references", "evidence_refs"}
_IDENTITIES = {"sample_id", "case_id", "aweme_id"}


def request_input_summary(evidence: dict | None, selected_ids=()) -> dict:
    evidence = evidence if isinstance(evidence, dict) else {}
    known = (evidence.get("version") == 1 and evidence.get("source") == "actual_request"
             and evidence.get("final_attempt") is True and isinstance(evidence.get("samples"), list))
    ids = set(selected_ids)
    rows = [row for row in evidence.get("samples", []) if isinstance(row, dict)
            and isinstance(row.get("sample_id"), str) and (not ids or row["sample_id"] in ids)] if known else []
    kinds = {name: set() for name in ("asr", "ocr", "comments", "prior_analysis")}
    images = set()
    direct = set()
    for row in rows:
        orders = row.get("image_orders")
        for order in orders if isinstance(orders, list) else []:
            if isinstance(order, int) and not isinstance(order, bool) and order > 0:
                images.add(order)
                direct.add(row["sample_id"])
        for material in row.get("materials", []) if isinstance(row.get("materials"), list) else []:
            if not isinstance(material, dict):
                continue
            chars = material.get("chars")
            if material.get("kind") in kinds and isinstance(chars, int) and not isinstance(chars, bool) and chars > 0:
                kinds[material["kind"]].add(row["sample_id"])
    return {"known": known, "source": "actual_request" if known else "historical_unknown",
            "sample_count": len({row["sample_id"] for row in rows}),
            "image_count": len(images), "direct_image_samples": len(direct),
            "without_direct_images": max(0, len(ids or {row["sample_id"] for row in rows}) - len(direct)),
            **{key: len(value) for key, value in kinds.items()}}


def input_scope_note(summary: dict) -> str:
    if not summary["known"]:
        return "本次输入范围未完整记录；已归档素材不代表本次模型实际使用过。"
    return (f"本次实际提交 {summary['image_count']} 张图，覆盖 {summary['direct_image_samples']} 条样本；"
            f"OCR 短摘 {summary['ocr']} 条、ASR 短摘 {summary['asr']} 条、有效评论 {summary['comments']} 条；"
            f"{summary['without_direct_images']} 条无直接图片输入。已有分析摘要 {summary['prior_analysis']} 条为二手材料，"
            "不等于本次直接查看原视频。引用可定位不代表结论已验证。")


def resolve_creator_references(raw: dict, samples) -> tuple[dict, dict, list[str]]:
    result = copy.deepcopy(raw)
    evidence = raw.get("request_evidence")
    summary = request_input_summary(evidence, [s.sample_id for s in samples])
    submitted = {row.get("sample_id") for row in evidence.get("samples", []) if isinstance(row, dict)} if summary["known"] else None
    eligible = [s for s in samples if submitted is None or s.sample_id in submitted]
    aliases, public = {}, []
    for sample in eligible:
        if not isinstance(sample.sample_id, str) or not _SAFE_ID.fullmatch(sample.sample_id):
            continue
        for key in _IDENTITIES:
            value = getattr(sample, key, "")
            if isinstance(value, str) and _SAFE_ID.fullmatch(value):
                aliases.setdefault(value, set()).add(sample.sample_id)
        case_id = sample.case_id if isinstance(sample.case_id, str) and _SAFE_ID.fullmatch(sample.case_id) else ""
        public.append({"sample_id": sample.sample_id, "title": sample.title or "样本名称未记录",
                       "case_id": case_id, "open_url": f"/cases/{case_id}" if case_id else ""})
    aliases = {key: next(iter(value)) for key, value in aliases.items() if len(value) == 1}
    entries, warnings = [], []
    prior = raw.get("reference_manifest") or {}
    prior_entries = prior.get("entries", []) if isinstance(prior, dict) and prior.get("version") == 1 else []

    def record(path, valid=(), invalid=()):
        # Preserve removed-reference diagnostics on reload, never restore support.
        old = next((entry for entry in prior_entries if isinstance(entry, dict) and entry.get("path") == path), {})
        invalid = [ref if isinstance(ref, str) and (_NARRATIVE_ID.fullmatch(ref) or re.fullmatch(r"\d{15,22}", ref)) else "invalid_reference" for ref in invalid]
        bad = list(dict.fromkeys([*invalid, *[ref for ref in old.get("invalid_refs", [])
                                            if isinstance(ref, str) and _SAFE_ID.fullmatch(ref) and ref not in aliases]]))
        good = list(dict.fromkeys(valid))
        entries.append({"path": path, "valid_sample_ids": good, "invalid_refs": bad,
                        "status": "partial" if good and bad else "invalid" if bad else "valid" if good else "none"})
        if bad:
            warnings.append(f"{path}：引用无法定位，需复核；已移除无效支持，不进行模糊纠错。")

    def walk(value, path):
        if isinstance(value, list):
            return [walk(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, str):
            refs = _NARRATIVE_ID.findall(value)
            if refs:
                record(path, [aliases[ref] for ref in refs if ref in aliases], [ref for ref in refs if ref not in aliases])
            return value  # Narrative originals remain auditable, not silently rewritten.
        if not isinstance(value, dict):
            return value
        cleaned = {}
        identity_values = {key: ref for key, ref in value.items() if key in _IDENTITIES and ref}
        if identity_values:
            resolved = {aliases.get(ref) for ref in identity_values.values() if isinstance(ref, str)}
            valid = len(resolved) == 1 and None not in resolved and len(identity_values) == sum(isinstance(ref, str) for ref in identity_values.values())
            record(path, resolved if valid else (), [str(ref) for ref in identity_values.values()] if not valid else ())
            if valid:
                sample_id = next(iter(resolved))
                sample = next(s for s in eligible if s.sample_id == sample_id)
                cleaned.update({key: getattr(sample, key) for key in identity_values})
                cleaned["sample_id"] = sample_id
                if "title" in value:
                    cleaned["title"] = sample.title or "样本名称未记录"
        for key, item in value.items():
            if key in _IDENTITIES or key == "title" and "title" in cleaned:
                continue
            child_path = f"{path}.{key}" if path else key
            if key in _REF_LISTS and isinstance(item, str):
                stripped = item.strip()
                if stripped.startswith(("[", "{")):
                    try:
                        decoded = json.loads(stripped)
                    except ValueError:
                        decoded = None
                    if isinstance(decoded, (list, dict)):
                        item = decoded
                elif stripped in aliases or _SAFE_ID.fullmatch(stripped):
                    item = [stripped]
            if key in _REF_LISTS and isinstance(item, dict):
                # A structured citation is equivalent to one entry in its list.
                item = [item]
            if key in _REF_LISTS and isinstance(item, list):
                valid_refs, invalid_refs, output = [], [], []
                for index, ref in enumerate(item):
                    if isinstance(ref, str):
                        if ref in aliases:
                            valid_refs.append(aliases[ref])
                            output.append(aliases[ref])
                        else:
                            invalid_refs.append(ref if _SAFE_ID.fullmatch(ref) else "invalid_reference")
                    elif isinstance(ref, dict):
                        entry_start = len(entries)
                        clean = walk(ref, f"{child_path}[{index}]")
                        if clean.get("sample_id") in aliases:
                            valid_refs.append(clean["sample_id"])
                            output.append(clean)
                        elif any(k in ref for k in _IDENTITIES):
                            invalid_refs.extend(str(ref[k]) for k in _IDENTITIES if ref.get(k))
                        else:
                            output.append(clean)
                            for entry in entries[entry_start:]:
                                valid_refs.extend(entry["valid_sample_ids"])
                                invalid_refs.extend(entry["invalid_refs"])
                cleaned[key] = output
                record(child_path, valid_refs, invalid_refs)
                if invalid_refs and "observation" in value:
                    note = "引用无法定位，需复核。"
                    uncertainty = str(value.get("uncertainty") or "")
                    cleaned["uncertainty"] = uncertainty if note in uncertainty else f"{uncertainty} {note}".strip()
            else:
                if key == "uncertainty" and key in cleaned:
                    continue
                cleaned[key] = walk(item, child_path)
        return cleaned

    for root in _ROOTS:
        if root in result:
            result[root] = walk(result[root], root)
    # Removed list members no longer have a traversable path on reload.
    visited = {entry["path"] for entry in entries}
    for entry in prior_entries:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"] not in visited and entry.get("invalid_refs"):
            record(entry["path"])
    manifest = {"version": 1, "scope": summary["source"],
                "identity_scope": "selected_and_submitted" if summary["known"] else "selected_only",
                "samples": public, "entries": sorted(entries, key=lambda row: row["path"])}
    result["reference_manifest"] = manifest
    return result, manifest, sorted(set(warnings))
