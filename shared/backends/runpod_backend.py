"""RunPod backend — 기존 runpod_client를 새 인터페이스로 감쌈."""
from __future__ import annotations

import logging
import os
import time
from contextlib import ExitStack
from pathlib import Path

from .base import GenerationJob, GenerationResult
from ..runpod_client import estimate_cost, runpod_audio_session

log = logging.getLogger(__name__)


class RunPodBackend:
    name = "runpod"

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.gpu_type: str = os.environ.get(
            "RUNPOD_GPU_TYPE", cfg.get("gpu_type", "NVIDIA RTX A5000")
        )
        self.image: str = os.environ.get(
            "AUDIOCRAFT_IMAGE", cfg.get("image", "runpod/audiocraft:latest")
        )
        self.volume_id: str | None = os.environ.get("RUNPOD_NETWORK_VOLUME_ID") or None
        self._stack: ExitStack | None = None
        self._pod = None

    def prepare(self, jobs: list[GenerationJob]) -> None:
        projected = self.estimate_cost(jobs)
        self._stack = ExitStack()
        self._pod = self._stack.enter_context(
            runpod_audio_session(
                name="audio-asset-local-proxy",
                gpu_type=self.gpu_type,
                image=self.image,
                volume_id=self.volume_id,
                required_budget_usd=projected + 0.5,
            )
        )

    def teardown(self) -> None:
        if self._stack is not None:
            self._stack.close()
        self._pod = None
        self._stack = None

    def estimate_cost(self, jobs: list[GenerationJob]) -> float:
        hours = len(jobs) * 0.005
        return estimate_cost(self.gpu_type, hours)

    def generate(self, job: GenerationJob) -> GenerationResult:
        import requests

        assert self._pod is not None, "prepare() 먼저 호출 필요"
        t0 = time.time()
        resp = requests.post(
            f"{self._pod.api_url}/generate",
            json={
                "model": job.model,
                "prompt": job.prompt,
                "duration": job.duration_ms / 1000.0,
                "seed": job.seed,
                "negative_prompt": job.negative_prompt,
                "cfg_scale": job.cfg_scale,
            },
            timeout=600,
        )
        resp.raise_for_status()
        job.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = job.output_dir / f"{job.prefix}.wav"
        out_path.write_bytes(resp.content)

        wall = time.time() - t0
        return GenerationResult(
            job_id=job.job_id,
            files=[out_path],
            backend=self.name,
            model=job.model,
            wall_sec=wall,
            cost_usd=estimate_cost(self.gpu_type, wall / 3600.0),
        )
