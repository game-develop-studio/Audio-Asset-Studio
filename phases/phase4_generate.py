"""Phase 4: Backend(local/warm/runpod)로 오디오 생성.

- 해시 캐시 히트 시 backend 미기동 (비용 0)
- 버짓 가드로 hard limit 초과 방지 (로컬/웜 backend는 cost=0이라 사실상 통과)
- finally 패턴으로 backend 확실히 teardown
- 시드 파밍 / 멀티플렉싱 / 레퍼런스 컨디셔닝 지원
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.backends import GenerationJob, get_backend
from shared.budget import BudgetGuard, BudgetState
from shared.cache import AssetCache
from shared.local_generator import generate_audio
from shared.pipeline_helpers import read_json, read_yaml, write_json

log = logging.getLogger(__name__)


def _run_job(backend, job: GenerationJob, raw_j: dict, target_lufs: float):
    """단일 job을 실행. multiplex / seed_farming 옵션 처리.

    Returns:
        (best_result, extra_dict)  — extra는 리포트에 병합될 메타
    """
    mux = raw_j.get("multiplex")
    farm = raw_j.get("seed_farming")

    if mux:
        from shared.multiplex import multiplex_generate
        best, all_res, scores = multiplex_generate(backend, job, mux, target_lufs)
        return best, {
            "variant": "multiplex",
            "picked_model": best.model,
            "picked_job_id": best.job_id,
            "candidates": [
                {"job_id": r.job_id, "model": r.model, "files": [str(p) for p in r.files],
                 "score": scores.get(r.job_id, {}).get("total", 0.0)}
                for r in all_res
            ],
            "scores": scores,
        }

    if farm:
        from shared.seed_farming import farm_seeds
        keep = int(raw_j.get("seed_farming_keep", 1))
        picks = farm_seeds(backend, job, count=int(farm), keep=keep, target_lufs=target_lufs)
        best_res, best_score = picks[0]
        return best_res, {
            "variant": "seed_farm",
            "farmed": int(farm),
            "kept": len(picks),
            "score": best_score,
            "picked_job_id": best_res.job_id,
            "candidates": [
                {"job_id": r.job_id, "files": [str(p) for p in r.files], "score": s.get("total", 0.0)}
                for r, s in picks
            ],
        }

    return backend.generate(job), {}


def _build_job(job_dict: dict, raw_dir: Path) -> GenerationJob:
    asset_dir = raw_dir / job_dict["asset_id"]
    ref = job_dict.get("reference_audio")
    return GenerationJob(
        job_id=job_dict["job_id"],
        asset_id=job_dict["asset_id"],
        model=job_dict["model"],
        prompt=job_dict["prompt"],
        duration_ms=int(job_dict["duration_ms"]),
        seed=int(job_dict.get("seed", 0)),
        output_dir=asset_dir,
        prefix=job_dict["job_id"],
        reference_audio=Path(ref) if ref else None,
        negative_prompt=job_dict.get("negative_prompt"),
        cfg_scale=float(job_dict.get("cfg_scale", 3.0)),
        extras=job_dict.get("extras", {}),
    )


def run(
    manifest_path: Path,
    pipeline_cfg_path: Path,
    out_dir: Path,
    backend_name: str | None = None,
    force: bool = False,
) -> Path:
    """generation manifest를 받아 오디오를 생성.

    Args:
        backend_name: "local" (default) | "warm" | "runpod". 환경변수 AUDIO_BACKEND도 인식.

    Returns:
        phase4_generation_report.json 경로
    """
    cfg = read_yaml(pipeline_cfg_path) if pipeline_cfg_path.exists() else {}
    manifest = read_json(manifest_path)
    project_id = manifest["project_id"]
    jobs = manifest["jobs"]

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cache_cfg = cfg.get("cache", {"enabled": True, "root": str(out_dir / ".cache")})
    cache = AssetCache(Path(cache_cfg["root"])) if cache_cfg.get("enabled", True) else None

    budget_cfg = cfg.get("budget", {"hard_limit_usd": 5.0, "soft_limit_pct": 0.8})
    budget = BudgetGuard(
        out_dir / "budget.json",
        BudgetState(
            project_id=project_id,
            hard_limit_usd=float(os.environ.get(
                "PROJECT_BUDGET_USD", budget_cfg.get("hard_limit_usd", 5.0)
            )),
            soft_limit_pct=float(os.environ.get(
                "BUDGET_SOFT_LIMIT_PCT", budget_cfg.get("soft_limit_pct", 0.8)
            )),
        ),
    )

    results: list[dict] = []
    pending_jobs: list[GenerationJob] = []
    pending_raw: list[dict] = []

    # 0) --force: 캐시 선-무효화
    if force and cache:
        invalidated = cache.invalidate_many([j["cache_key"] for j in jobs])
        log.info("--force: invalidated %d cache entries", invalidated)

    # 1) 캐시 히트 확인
    for j in jobs:
        asset_dir = raw_dir / j["asset_id"]
        if cache and not force:
            restored = cache.restore(j["cache_key"], asset_dir)
            if restored:
                results.append({
                    "job_id": j["job_id"],
                    "asset_id": j["asset_id"],
                    "status": "cached",
                    "files": [str(p) for p in restored],
                })
                continue
        pending_raw.append(j)
        pending_jobs.append(_build_job(j, raw_dir))

    if not pending_jobs:
        log.info("Phase 4: all jobs cached")
        out = out_dir / "phase4_generation_report.json"
        write_json(out, {
            "project_id": project_id,
            "results": results,
            "backend": "cache",
            "budget_spent": 0.0,
        })
        return out

    # 2) backend 결정
    backend_name = (
        backend_name
        or os.environ.get("AUDIO_BACKEND")
        or cfg.get("backend", "local")
    )
    backend_cfg = cfg.get(backend_name, {}) if isinstance(cfg.get(backend_name), dict) else {}
    # 하위 호환: runpod 설정은 top-level runpod 블록에 있을 수 있음
    if backend_name == "runpod" and "runpod" in cfg:
        backend_cfg = {**cfg.get("runpod", {}), **backend_cfg}
    backend = get_backend(backend_name, backend_cfg)

    projected = backend.estimate_cost(pending_jobs)
    if projected > 0:
        budget.check(projected)

    log.info(
        "Phase 4: backend=%s, %d jobs, est=$%.4f",
        backend.name, len(pending_jobs), projected,
    )

    # 3) 생성 루프
    target_lufs = float(os.environ.get("LOUDNESS_TARGET_LUFS", cfg.get("loudness_target", -14.0)))

    try:
        backend.prepare(pending_jobs)
        for raw_j, job in zip(pending_raw, pending_jobs):
            try:
                res, extra = _run_job(backend, job, raw_j, target_lufs)
            except Exception as e:
                log.error("Generation failed for %s: %s", job.job_id, e)
                results.append({
                    "job_id": job.job_id,
                    "asset_id": job.asset_id,
                    "status": "failed",
                    "error": str(e),
                })
                continue

            if cache and res.files:
                cache.put(raw_j["cache_key"], res.files)
            if res.cost_usd > 0:
                budget.charge(res.cost_usd, reason=job.job_id)

            entry = {
                "job_id": job.job_id,
                "asset_id": job.asset_id,
                "status": "generated",
                "files": [str(p) for p in res.files],
                "backend": res.backend,
                "wall_sec": round(res.wall_sec, 2),
            }
            entry.update(extra)
            results.append(entry)
    finally:
        backend.teardown()

    out = out_dir / "phase4_generation_report.json"
    write_json(out, {
        "project_id": project_id,
        "results": results,
        "backend": backend.name,
        "budget_spent": budget.state.spent_usd,
    })
    log.info(
        "Phase 4 done: %d results, spent $%.4f (backend=%s)",
        len(results), budget.state.spent_usd, backend.name,
    )
    return out
