"""모델 멀티플렉싱 — 동일 프롬프트를 여러 모델에 발주 후 자동 A/B.

phase3 manifest에서 job에 `multiplex: [model1, model2, ...]` 필드가 있으면
phase4가 각 모델로 생성 → CLAP+LUFS 스코어로 1개 채택.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from .backends.base import Backend, GenerationJob, GenerationResult

log = logging.getLogger(__name__)


def multiplex_generate(
    backend: Backend,
    base_job: GenerationJob,
    models: list[str],
    target_lufs: float = -14.0,
) -> tuple[GenerationResult, list[GenerationResult], dict]:
    """여러 모델로 생성 후 최고 스코어 1개 채택.

    Returns:
        (best_result, all_results, scores_by_job)
    """
    from .scoring import combined_score

    all_results: list[GenerationResult] = []
    scores: dict[str, dict] = {}

    for m in models:
        mux_job = replace(
            base_job,
            model=m,
            prefix=f"{base_job.prefix}__{m.replace('/', '_')}",
            output_dir=base_job.output_dir / "mux",
        )
        try:
            res = backend.generate(mux_job)
        except Exception as e:
            log.warning("multiplex[%s] 실패: %s", m, e)
            continue
        all_results.append(res)
        if res.files:
            scores[res.job_id] = combined_score(res.files[0], base_job.prompt, target_lufs)

    if not all_results:
        raise RuntimeError(f"multiplex: all {len(models)} models failed")

    best_id = max(scores, key=lambda k: scores[k]["total"]) if scores else all_results[0].job_id
    best = next(r for r in all_results if r.job_id == best_id)
    return best, all_results, scores
