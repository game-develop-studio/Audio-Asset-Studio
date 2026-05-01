"""Phase 5: 후처리 체인 실행.

Phase 4에서 생성된 raw 오디오에 normalize/trim/fade/loop/layer_mix/format_convert를 적용.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from shared.pipeline_helpers import read_json, write_json

log = logging.getLogger(__name__)


def _run_post_chain(
    audio_path: Path,
    chain: list[str],
    asset_meta: dict,
    output_dir: Path,
) -> Path:
    """단일 파일에 후처리 체인을 순차 적용."""
    from post_process.normalize import normalize
    from post_process.trim import trim_silence
    from post_process.fade import apply_fade
    from post_process.loop import apply_loop_crossfade
    from post_process.format_convert import convert_format

    current = audio_path
    for step in chain:
        if step == "normalize":
            platform = asset_meta.get("loudness_platform")
            target = asset_meta.get("target_lufs", -14.0)
            current = normalize(current, target_dbfs=target, platform=platform)
        elif step == "trim":
            current = trim_silence(current)
        elif step == "fade":
            current = apply_fade(current)
        elif step == "loop_detect":
            pass  # loop_crossfade에서 같이 처리
        elif step == "loop_crossfade":
            current = apply_loop_crossfade(current, bpm=asset_meta.get("bpm"))
        elif step == "format_convert":
            target_fmt = asset_meta.get("format", "ogg")
            channels = 1 if asset_meta.get("channels") == "mono" else 2
            current = convert_format(
                current,
                target_format=target_fmt,
                sample_rate=asset_meta.get("sample_rate", 44100),
                channels=channels,
            )
        elif step == "auto_tag":
            from post_process.audio_tagger import matches_category
            cat = asset_meta.get("category", "")
            passed, score, ranked = matches_category(current, cat, threshold=0.15)
            asset_meta.setdefault("_tags", {})["ranked"] = ranked
            asset_meta["_tags"]["passed"] = passed
            asset_meta["_tags"]["score"] = score
            if not passed:
                log.warning("Tag mismatch %s: category=%s ranked=%s", current.name, cat, ranked[:3])
        elif step == "stem_split":
            from post_process.stem_split import split_stems, build_intensity_layers
            stems = split_stems(current, current.parent / "stems")
            layers = build_intensity_layers(stems, current.parent / "intensity", current.stem)
            asset_meta.setdefault("_stems", {})["files"] = {k: str(v) for k, v in stems.items()}
            asset_meta["_stems"]["intensity"] = {k: str(v) for k, v in layers.items()}
        else:
            log.warning("Unknown post-process step: %s", step)

    return current


def run(
    report_path: Path,
    manifest_path: Path,
    out_dir: Path,
) -> Path:
    """Phase 4 리포트를 받아 후처리를 수행.

    Returns:
        phase5_post_process_report.json 경로
    """
    report = read_json(report_path)
    manifest = read_json(manifest_path)
    assets_meta = manifest.get("assets_meta", {})

    processed_dir = out_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    # 레이어 그룹핑: asset_id+variation → 레이어 파일 목록
    layer_groups: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))

    for entry in report.get("results", []):
        if entry.get("status") not in ("generated", "cached"):
            results.append(entry)
            continue

        asset_id = entry["asset_id"]
        meta = assets_meta.get(asset_id, {})
        chain = meta.get("post_process", [])

        for fpath_str in entry.get("files", []):
            fpath = Path(fpath_str)
            if not fpath.exists():
                log.warning("File not found: %s", fpath)
                continue

            processed = _run_post_chain(fpath, chain, meta, processed_dir)

            # 레이어 그룹핑 (layer_mix용)
            layers = meta.get("layers")
            if layers:
                # job_id 에서 레이어명과 variation 추출: hero_walk_impact_v1
                job_id = entry["job_id"]
                parts = job_id.rsplit("_v", 1)
                if len(parts) == 2:
                    layer_part = parts[0].replace(f"{asset_id}_", "")
                    var_key = f"{asset_id}_v{parts[1]}"
                    layer_groups[var_key][layer_part].append(processed)

            results.append({
                "job_id": entry["job_id"],
                "asset_id": asset_id,
                "status": "processed",
                "original": fpath_str,
                "processed": str(processed),
                "_tags": meta.get("_tags"),
                "_stems": meta.get("_stems"),
            })

    # 레이어 믹스다운
    mix_results: list[dict] = []
    if layer_groups:
        from post_process.layer_mix import mix_layers

        for var_key, layer_files_dict in layer_groups.items():
            asset_id = var_key.rsplit("_v", 1)[0]
            meta = assets_meta.get(asset_id, {})
            fmt = meta.get("format", "ogg")

            # layer_files: {"impact": Path, "sweetener": Path, ...}
            single_files: dict[str, Path] = {}
            for layer_name, paths in layer_files_dict.items():
                if paths:
                    single_files[layer_name] = paths[0]

            if len(single_files) > 1:
                mix_out = processed_dir / f"{var_key}_mixed.{fmt}"
                mixed = mix_layers(single_files, mix_out)
                mix_results.append({
                    "asset_id": asset_id,
                    "variation": var_key,
                    "status": "mixed",
                    "layers": list(single_files.keys()),
                    "output": str(mixed),
                })

    out = out_dir / "phase5_post_process_report.json"
    write_json(out, {
        "project_id": report.get("project_id", ""),
        "results": results,
        "layer_mixes": mix_results,
    })
    log.info("Phase 5 done: %d processed, %d layer mixes", len(results), len(mix_results))
    return out
