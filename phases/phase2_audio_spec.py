"""Phase 2: 사운드 명세 정규화 + 비용 추정."""
from __future__ import annotations

import logging
from pathlib import Path

from shared.pipeline_helpers import read_json, read_yaml, write_json

log = logging.getLogger(__name__)

LOUDNESS_PLATFORM_PRESETS = {
    "mobile": -14.0,
    "console": -16.0,
    "pc": -18.0,
    "broadcast": -23.0,
}


def run(
    project_id: str,
    user_input: dict,
    palette_path: Path,
    out_dir: Path,
    categories_cfg_path: Path,
    loudness_target: float | None = None,
    loudness_platform: str | None = None,
) -> Path:
    """에셋 명세를 정규화하고 비용을 추정한다.

    Returns:
        phase2_audio_spec.json 경로
    """
    palette = read_json(palette_path)
    cats_cfg = read_yaml(categories_cfg_path).get("categories", {})
    cost_cfg = read_yaml(categories_cfg_path).get("cost_estimation", {})
    output_cfg = user_input.get("audio_output", {})
    effective_platform = loudness_platform or output_cfg.get("loudness_platform")
    effective_target_lufs = (
        loudness_target
        if loudness_target is not None
        else output_cfg.get("target_lufs")
    )
    if effective_target_lufs is None and effective_platform in LOUDNESS_PLATFORM_PRESETS:
        effective_target_lufs = LOUDNESS_PLATFORM_PRESETS[effective_platform]

    assets_input = user_input.get("assets", [])
    normalized: list[dict] = []
    total_gen_seconds = 0

    for a in assets_input:
        cat = a["category"]
        if cat not in cats_cfg:
            raise ValueError(f"Unknown audio category: {cat}. Available: {list(cats_cfg.keys())}")

        cat_cfg = cats_cfg[cat]
        variations = a.get("variations", cat_cfg.get("default_variations", 1))

        # duration 결정: duration_sec → duration_ms → category default
        if a.get("duration_sec"):
            duration_ms = a["duration_sec"] * 1000
        elif a.get("duration_ms"):
            duration_ms = a["duration_ms"]
        else:
            duration_ms = cat_cfg["default_duration_ms"]

        fmt = a.get("format", cat_cfg.get("default_format", "ogg"))
        model = a.get("model", cat_cfg.get("model", "audiogen"))

        # 프롬프트 접미사 적용
        prompt = a.get("prompt", "")
        prompt_suffix = cat_cfg.get("prompt_suffix", "")
        if prompt and prompt_suffix:
            prompt = prompt + prompt_suffix

        # 팔레트 프롬프트 수식어 prepend
        modifiers = palette.get("prompt_modifiers", {})
        global_prefix = modifiers.get("global_prefix", "")
        type_prefix = modifiers.get("sfx_prefix", "") if cat.startswith("sfx_") else modifiers.get("bgm_prefix", "")
        if global_prefix or type_prefix:
            prefix = ", ".join(filter(None, [global_prefix, type_prefix]))
            if prefix:
                prompt = f"{prefix}, {prompt}" if prompt else prefix

        # 후처리 체인 결정
        post_process = a.get("post_process", cat_cfg.get("post_process", []))

        entry = {
            "asset_id": a["asset_id"],
            "category": cat,
            "prompt": prompt,
            "variations": variations,
            "duration_ms": duration_ms,
            "format": fmt,
            "loop": a.get("loop", False),
            "bpm": a.get("bpm"),
            "layers": a.get("layers"),
            "intensity_layers": a.get("intensity_layers"),
            "model": model,
            "channels": a.get("channels", cat_cfg.get("channels", "mono")),
            "sample_rate": a.get("sample_rate", cat_cfg.get("sample_rate", 44100)),
            "post_process": post_process,
            "seed_farming": a.get("seed_farming"),
            "seed_farming_keep": a.get("seed_farming_keep"),
            "multiplex": a.get("multiplex"),
            "reference_audio": a.get("reference_audio"),
            "negative_prompt": a.get("negative_prompt"),
            "cfg_scale": a.get("cfg_scale"),
            "loudness_platform": effective_platform,
            "target_lufs": effective_target_lufs,
        }
        normalized.append(entry)

        # 비용 추정: 레이어 있으면 레이어 수 × variations
        layer_count = len(a.get("layers", [])) if a.get("layers") else 1
        gen_count = variations * layer_count
        sec_per = cost_cfg.get(
            f"{model}_sec_per_asset",
            45 if model == "musicgen" else 15,
        )
        total_gen_seconds += gen_count * sec_per

    hours = total_gen_seconds / 3600
    estimated_cost_usd = round(hours * float(cost_cfg.get("gpu_cost_usd_per_hour", 0.0)), 4)

    spec = {
        "project_id": project_id,
        "palette": palette.get("name", "default"),
        "assets": normalized,
        "estimated_total_generations": sum(
            a["variations"] * (len(a.get("layers") or []) or 1) for a in normalized
        ),
        "estimated_gen_hours": round(hours, 4),
        "estimated_cost_usd": estimated_cost_usd,
        "backend": "local",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase2_audio_spec.json"
    write_json(out, spec)
    log.info(
        "Phase 2 done: %d assets, ~%.3fh (local)",
        len(normalized), hours,
    )
    return out
