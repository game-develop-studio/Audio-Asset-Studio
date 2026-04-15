"""Backend 공통 인터페이스."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class GenerationJob:
    job_id: str
    asset_id: str
    model: str                  # "musicgen-small" | "musicgen-medium" | "musicgen-large"
                                # | "musicgen-melody" | "audiogen-medium" | "stable-audio-open"
    prompt: str
    duration_ms: int
    seed: int
    output_dir: Path
    prefix: str
    reference_audio: Path | None = None      # melody conditioning
    negative_prompt: str | None = None
    cfg_scale: float = 3.0
    extras: dict = field(default_factory=dict)


@dataclass
class GenerationResult:
    job_id: str
    files: list[Path]
    backend: str
    model: str
    wall_sec: float
    cost_usd: float = 0.0


class Backend(Protocol):
    name: str

    def prepare(self, jobs: list[GenerationJob]) -> None:
        """세션 준비 (모델 로드, Pod 기동 등)."""

    def generate(self, job: GenerationJob) -> GenerationResult:
        """단일 job 실행."""

    def teardown(self) -> None:
        """세션 종료 (Pod 종료 등)."""

    def estimate_cost(self, jobs: list[GenerationJob]) -> float:
        """전체 예상 비용 USD."""


def get_backend(name: str, cfg: dict) -> Backend:
    """Backend factory. 이름으로 적절한 어댑터 반환."""
    name = (name or "local").lower()
    if name == "local":
        from .local_backend import LocalBackend
        return LocalBackend(cfg)
    if name == "warm":
        from .warm_backend import WarmPoolBackend
        return WarmPoolBackend(cfg)
    if name == "runpod":
        from .runpod_backend import RunPodBackend
        return RunPodBackend(cfg)
    raise ValueError(f"Unknown backend: {name}")
