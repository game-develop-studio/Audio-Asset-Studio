"""시드 파밍 — 동일 프롬프트에 N개 시드로 생성, 클러스터링 후 대표 채택."""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from .backends.base import Backend, GenerationJob, GenerationResult

log = logging.getLogger(__name__)


def farm_seeds(
    backend: Backend,
    base_job: GenerationJob,
    count: int = 6,
    keep: int = 1,
    target_lufs: float = -14.0,
) -> list[tuple[GenerationResult, dict]]:
    """N개 시드 생성 후 CLAP 클러스터링으로 `keep`개 대표 선택.

    Returns: [(result, score_dict), ...] 길이 <= keep
    """
    from .scoring import cluster_and_pick

    results: list[GenerationResult] = []
    for i in range(count):
        seed_job = replace(
            base_job,
            seed=base_job.seed + i * 7919,  # 프라임 간격
            prefix=f"{base_job.prefix}__s{i}",
            output_dir=base_job.output_dir / "seeds",
        )
        try:
            results.append(backend.generate(seed_job))
        except Exception as e:
            log.warning("seed %d 실패: %s", i, e)

    if not results:
        raise RuntimeError("seed farming: all seeds failed")

    files = [r.files[0] for r in results if r.files]
    picks = cluster_and_pick(files, base_job.prompt, k=min(keep, len(files)), target_lufs=target_lufs)

    # 파일 경로 → result 매핑
    path_to_res = {r.files[0]: r for r in results if r.files}
    return [(path_to_res[p], score) for p, score in picks if p in path_to_res]
