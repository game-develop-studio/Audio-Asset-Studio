"""Phase 3: 모델별 프롬프트 빌드.

Phase 2의 정규화된 명세를 받아, 각 에셋(+레이어+배리에이션)별로
실제 모델에 전달할 generation job 목록을 만든다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from shared.cache import hash_params
from shared.pipeline_helpers import read_json, write_json

log = logging.getLogger(__name__)

# 레이어별 프롬프트 힌트
LAYER_PROMPT_HINTS = {
    "impact": "punchy impact, heavy thud, initial hit",
    "sweetener": "bright sweetener, sparkle, high detail accent",
    "tail": "reverb tail, lingering decay, aftermath",
    "whoosh": "fast whoosh, air movement, swipe",
    "ring": "metallic ring, resonant tone, sustain",
}


def _build_jobs_for_asset(asset: dict) -> list[dict]:
    """단일 에셋에 대해 generation job 목록을 생성."""
    jobs: list[dict] = []
    layers = asset.get("layers")
    intensity_layers = asset.get("intensity_layers")

    if intensity_layers:
        # 적응형 BGM: 인텐시티 레이어별 생성
        for il in intensity_layers:
            for v in range(asset["variations"]):
                job = {
                    "asset_id": asset["asset_id"],
                    "job_id": f"{asset['asset_id']}_{il['level']}_v{v+1}",
                    "model": asset["model"],
                    "prompt": il["prompt"],
                    "duration_ms": asset["duration_ms"],
                    "seed": v + 1,
                    "layer": il["level"],
                    "is_intensity_layer": True,
                }
                job["cache_key"] = hash_params({
                    "asset": job["asset_id"],
                    "job": job["job_id"],
                    "prompt": job["prompt"],
                    "duration": job["duration_ms"],
                    "seed": job["seed"],
                })
                jobs.append(job)
    elif layers:
        # 레이어드 SFX: 레이어별 × 배리에이션
        for layer_name in layers:
            hint = LAYER_PROMPT_HINTS.get(layer_name, layer_name)
            layer_prompt = f"{asset['prompt']}, {hint}" if asset.get("prompt") else hint
            for v in range(asset["variations"]):
                job = {
                    "asset_id": asset["asset_id"],
                    "job_id": f"{asset['asset_id']}_{layer_name}_v{v+1}",
                    "model": asset["model"],
                    "prompt": layer_prompt,
                    "duration_ms": asset["duration_ms"],
                    "seed": v + 1,
                    "layer": layer_name,
                    "is_intensity_layer": False,
                }
                job["cache_key"] = hash_params({
                    "asset": job["asset_id"],
                    "job": job["job_id"],
                    "prompt": job["prompt"],
                    "duration": job["duration_ms"],
                    "seed": job["seed"],
                })
                jobs.append(job)
    else:
        # 단일 생성
        for v in range(asset["variations"]):
            job = {
                "asset_id": asset["asset_id"],
                "job_id": f"{asset['asset_id']}_v{v+1}",
                "model": asset["model"],
                "prompt": asset.get("prompt", ""),
                "duration_ms": asset["duration_ms"],
                "seed": v + 1,
                "layer": None,
                "is_intensity_layer": False,
            }
            job["cache_key"] = hash_params({
                "asset": job["asset_id"],
                "job": job["job_id"],
                "prompt": job["prompt"],
                "duration": job["duration_ms"],
                "seed": job["seed"],
            })
            jobs.append(job)

    return jobs


def run(
    spec_path: Path,
    out_dir: Path,
) -> Path:
    """Phase 2 스펙을 받아 generation manifest를 생성.

    Returns:
        phase3_generation_manifest.json 경로
    """
    spec = read_json(spec_path)
    all_jobs: list[dict] = []

    for asset in spec["assets"]:
        jobs = _build_jobs_for_asset(asset)
        all_jobs.extend(jobs)

    manifest = {
        "project_id": spec["project_id"],
        "total_jobs": len(all_jobs),
        "jobs": all_jobs,
        "assets_meta": {
            a["asset_id"]: {
                "category": a["category"],
                "format": a["format"],
                "loop": a.get("loop", False),
                "bpm": a.get("bpm"),
                "channels": a.get("channels", "mono"),
                "sample_rate": a.get("sample_rate", 44100),
                "post_process": a.get("post_process", []),
                "layers": a.get("layers"),
            }
            for a in spec["assets"]
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase3_generation_manifest.json"
    write_json(out, manifest)
    log.info("Phase 3 done: %d generation jobs for %d assets", len(all_jobs), len(spec["assets"]))
    return out
