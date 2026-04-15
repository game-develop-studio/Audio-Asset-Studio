"""WarmPoolBackend — model_server(HTTP)로 생성 요청 위임.

장점: 파이프라인 프로세스가 재시작돼도 모델은 상주 → 콜드스타트 0.
model_server는 `python -m shared.model_server` 로 띄움.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path

from .base import GenerationJob, GenerationResult

log = logging.getLogger(__name__)


class WarmPoolBackend:
    name = "warm"

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.endpoint: str = os.environ.get(
            "MODEL_SERVER_URL", cfg.get("endpoint", "http://127.0.0.1:8765")
        )
        self.timeout: int = int(cfg.get("timeout", 600))

    def prepare(self, jobs: list[GenerationJob]) -> None:
        import requests

        try:
            r = requests.get(f"{self.endpoint}/health", timeout=5)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(
                f"model_server({self.endpoint}) 응답 없음. "
                f"`python -m shared.model_server` 로 먼저 띄워주세요. ({e})"
            ) from e

    def teardown(self) -> None:
        pass

    def estimate_cost(self, jobs: list[GenerationJob]) -> float:
        return 0.0

    def generate(self, job: GenerationJob) -> GenerationResult:
        import requests

        payload = {
            "job_id": job.job_id,
            "model": job.model,
            "prompt": job.prompt,
            "duration_ms": job.duration_ms,
            "seed": job.seed,
            "cfg_scale": job.cfg_scale,
            "negative_prompt": job.negative_prompt,
            "prefix": job.prefix,
        }
        if job.reference_audio and Path(job.reference_audio).exists():
            payload["reference_audio_b64"] = base64.b64encode(
                Path(job.reference_audio).read_bytes()
            ).decode()

        t0 = time.time()
        r = requests.post(f"{self.endpoint}/generate", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        job.output_dir.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        for name, b64 in data["files"].items():
            p = job.output_dir / name
            p.write_bytes(base64.b64decode(b64))
            files.append(p)

        return GenerationResult(
            job_id=job.job_id,
            files=files,
            backend=self.name,
            model=job.model,
            wall_sec=time.time() - t0,
            cost_usd=0.0,
        )
