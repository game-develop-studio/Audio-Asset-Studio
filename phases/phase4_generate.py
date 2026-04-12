"""Phase 4: 로컬 AudioCraft/MusicGen으로 오디오 생성.

- 해시 캐시 히트 시 모델 미로딩 (비용 0)
- Mac Studio MPS 가속 활용
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.budget import BudgetGuard, BudgetState
from shared.cache import AssetCache
from shared.local_generator import generate_audio
from shared.pipeline_helpers import read_json, read_yaml, write_json

log = logging.getLogger(__name__)


def run(
    manifest_path: Path,
    pipeline_cfg_path: Path,
    out_dir: Path,
) -> Path:
    """generation manifest를 받아 오디오를 생성.

    Returns:
        phase4_generation_report.json 경로
    """
    cfg = read_yaml(pipeline_cfg_path)
    manifest = read_json(manifest_path)
    project_id = manifest["project_id"]
    jobs = manifest["jobs"]

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 캐시 설정
    cache_cfg = cfg.get("cache", {"enabled": True, "root": str(out_dir / ".cache")})
    cache = AssetCache(Path(cache_cfg["root"])) if cache_cfg.get("enabled", True) else None

    # 버짓 설정 (로컬이라 비용 0이지만 추적용으로 유지)
    budget_cfg = cfg.get("budget", {"hard_limit_usd": 5.0, "soft_limit_pct": 0.8})
    budget = BudgetGuard(
        out_dir / "budget.json",
        BudgetState(
            project_id=project_id,
            hard_limit_usd=float(os.environ.get("PROJECT_BUDGET_USD", budget_cfg.get("hard_limit_usd", 5.0))),
            soft_limit_pct=float(os.environ.get("BUDGET_SOFT_LIMIT_PCT", budget_cfg.get("soft_limit_pct", 0.8))),
        ),
    )

    results: list[dict] = []
    pending: list[dict] = []

    # 1단계: 캐시 확인
    for job in jobs:
        asset_dir = raw_dir / job["asset_id"]
        if cache:
            restored = cache.restore(job["cache_key"], asset_dir)
            if restored:
                results.append({
                    "job_id": job["job_id"],
                    "asset_id": job["asset_id"],
                    "status": "cached",
                    "files": [str(p) for p in restored],
                })
                continue
        pending.append(job)

    if not pending:
        log.info("Phase 4: all jobs cached, skipping generation")
        out = out_dir / "phase4_generation_report.json"
        write_json(out, {
            "project_id": project_id,
            "results": results,
            "local": True,
        })
        return out

    # 2단계: 로컬 생성
    log.info("Phase 4: %d jobs to generate locally (MPS/CPU)", len(pending))

    for job in pending:
        asset_dir = raw_dir / job["asset_id"]
        asset_dir.mkdir(parents=True, exist_ok=True)

        log.info("Generating %s (model=%s)", job["job_id"], job["model"])
        try:
            files = generate_audio(
                prompt=job["prompt"],
                model_name=job["model"],
                duration_ms=job["duration_ms"],
                seed=job["seed"],
                output_dir=asset_dir,
                prefix=job["job_id"],
            )
        except Exception as e:
            log.error("Generation failed for %s: %s", job["job_id"], e)
            results.append({
                "job_id": job["job_id"],
                "asset_id": job["asset_id"],
                "status": "failed",
                "error": str(e),
            })
            continue

        if cache and files:
            cache.put(job["cache_key"], files)

        results.append({
            "job_id": job["job_id"],
            "asset_id": job["asset_id"],
            "status": "generated",
            "files": [str(p) for p in files],
        })

    out = out_dir / "phase4_generation_report.json"
    write_json(out, {
        "project_id": project_id,
        "results": results,
        "local": True,
    })
    log.info("Phase 4 done: %d generated locally", len(results))
    return out
