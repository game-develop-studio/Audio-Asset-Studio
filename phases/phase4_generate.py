"""Phase 4: RunPod GPU에서 AudioCraft/MusicGen으로 오디오 생성.

- 해시 캐시 히트 시 Pod 미기동 (비용 0)
- 버짓 가드로 hard limit 초과 방지
- finally 패턴으로 Pod 확실히 종료
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.budget import BudgetGuard, BudgetState
from shared.cache import AssetCache
from shared.pipeline_helpers import read_json, read_yaml, write_json
from shared.runpod_client import RunPodClient, estimate_cost, runpod_audio_session

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

    # 버짓 설정
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
        log.info("Phase 4: all jobs cached, skipping RunPod")
        out = out_dir / "phase4_generation_report.json"
        write_json(out, {
            "project_id": project_id,
            "results": results,
            "pod_used": False,
        })
        return out

    # 2단계: 버짓 예상 차감
    gpu_type = os.environ.get("RUNPOD_GPU_TYPE", cfg.get("runpod", {}).get("gpu_type", "NVIDIA RTX A5000"))
    est_hours = len(pending) * 0.005
    projected = estimate_cost(gpu_type, est_hours)
    budget.check(projected)

    # 3단계: Pod 세션 + 실행
    image = os.environ.get("AUDIOCRAFT_IMAGE", cfg.get("runpod", {}).get("image", "runpod/audiocraft:latest"))
    volume_id = os.environ.get("RUNPOD_NETWORK_VOLUME_ID") or None

    with runpod_audio_session(
        name=f"audio-asset-{project_id}",
        gpu_type=gpu_type,
        image=image,
        volume_id=volume_id,
        required_budget_usd=projected + 0.5,
    ) as pod:
        for job in pending:
            asset_dir = raw_dir / job["asset_id"]
            asset_dir.mkdir(parents=True, exist_ok=True)

            log.info("Generating %s (model=%s)", job["job_id"], job["model"])
            try:
                # AudioCraft HTTP API 호출
                # 실제 구현은 pod.api_url + /generate 엔드포인트
                files = _generate_audio(
                    api_url=pod.api_url,
                    prompt=job["prompt"],
                    model=job["model"],
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
            budget.charge(estimate_cost(gpu_type, 0.005), reason=job["job_id"])

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
        "pod_used": True,
        "budget_spent": budget.state.spent_usd,
    })
    log.info("Phase 4 done: %d generated, spent $%.4f", len(results), budget.state.spent_usd)
    return out


def _generate_audio(
    api_url: str,
    prompt: str,
    model: str,
    duration_ms: int,
    seed: int,
    output_dir: Path,
    prefix: str,
) -> list[Path]:
    """AudioCraft HTTP API로 오디오 생성 (실사용 시 구현 필요).

    Returns:
        생성된 WAV 파일 경로 리스트
    """
    import requests

    resp = requests.post(
        f"{api_url}/generate",
        json={
            "model": model,
            "prompt": prompt,
            "duration": duration_ms / 1000.0,
            "seed": seed,
        },
        timeout=300,
    )
    resp.raise_for_status()

    out_path = output_dir / f"{prefix}.wav"
    out_path.write_bytes(resp.content)
    return [out_path]
