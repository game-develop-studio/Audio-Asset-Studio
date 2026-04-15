"""LocalBackend — MPS/CUDA/CPU 로컬 추론.

모델별 어댑터를 lazy-load하고 세션 내에서 재사용 (프로세스 내 웜풀).
여러 모델을 오가면 VRAM 압박이 있으므로 `unload_between_models` 옵션 제공.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .base import GenerationJob, GenerationResult
from .local.registry import load_adapter

log = logging.getLogger(__name__)


class LocalBackend:
    name = "local"

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.unload_between_models: bool = bool(cfg.get("unload_between_models", False))
        self._adapters: dict[str, object] = {}

    # ---- lifecycle ----
    def prepare(self, jobs: list[GenerationJob]) -> None:
        # 사용 모델 목록 미리 파악만 — 실제 로드는 첫 generate 호출 시
        models = {j.model for j in jobs}
        log.info("LocalBackend: %d jobs, models=%s", len(jobs), sorted(models))

    def teardown(self) -> None:
        for ad in self._adapters.values():
            try:
                ad.unload()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._adapters.clear()

    def estimate_cost(self, jobs: list[GenerationJob]) -> float:
        return 0.0  # 전기세 빼곤 0

    # ---- generation ----
    def _get_adapter(self, model: str):
        if self.unload_between_models:
            for k, ad in list(self._adapters.items()):
                if k != model:
                    try:
                        ad.unload()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    self._adapters.pop(k, None)
        if model not in self._adapters:
            self._adapters[model] = load_adapter(model)
        return self._adapters[model]

    def generate(self, job: GenerationJob) -> GenerationResult:
        adapter = self._get_adapter(job.model)
        t0 = time.time()
        files = adapter.generate(  # type: ignore[attr-defined]
            prompt=job.prompt,
            duration_ms=job.duration_ms,
            seed=job.seed,
            output_dir=Path(job.output_dir),
            prefix=job.prefix,
            reference_audio=job.reference_audio,
            cfg_scale=job.cfg_scale,
            negative_prompt=job.negative_prompt,
        )
        return GenerationResult(
            job_id=job.job_id,
            files=files,
            backend=self.name,
            model=job.model,
            wall_sec=time.time() - t0,
            cost_usd=0.0,
        )
