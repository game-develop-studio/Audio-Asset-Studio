"""RunPod 클라이언트 — AudioCraft/MusicGen Pod 관리."""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

log = logging.getLogger(__name__)

# GPU 가격 ($/hr)
GPU_PRICING = {
    "NVIDIA RTX A5000": 0.44,
    "NVIDIA RTX A4000": 0.32,
    "NVIDIA A40": 0.79,
    "NVIDIA RTX 4090": 0.74,
}


def estimate_cost(gpu_type: str, hours: float) -> float:
    rate = GPU_PRICING.get(gpu_type, 0.50)
    return round(rate * hours, 4)


@dataclass
class PodInfo:
    pod_id: str
    api_url: str
    gpu_type: str


class RunPodClient:
    """RunPod GraphQL API 클라이언트."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY", "")

    def create_pod(
        self,
        name: str,
        gpu_type: str,
        image: str,
        volume_id: str | None = None,
    ) -> PodInfo:
        log.info("Creating RunPod: %s (GPU=%s, image=%s)", name, gpu_type, image)
        # 실제 구현은 RunPod GraphQL API 호출
        # 여기서는 인터페이스만 정의
        raise NotImplementedError("RunPod API 호출 — 실사용 시 RUNPOD_API_KEY 필요")

    def terminate_pod(self, pod_id: str) -> None:
        log.info("Terminating pod: %s", pod_id)
        raise NotImplementedError("RunPod API 호출")

    def wait_ready(self, pod_id: str, timeout: int = 300) -> str:
        raise NotImplementedError("RunPod API 호출")


@contextmanager
def runpod_audio_session(
    name: str,
    gpu_type: str,
    image: str,
    volume_id: str | None = None,
    required_budget_usd: float = 1.0,
) -> Generator[PodInfo, None, None]:
    """Pod 세션 컨텍스트 매니저 — finally 패턴으로 Pod 확실히 종료."""
    client = RunPodClient()
    pod = client.create_pod(name, gpu_type, image, volume_id)
    try:
        api_url = client.wait_ready(pod.pod_id)
        pod.api_url = api_url
        yield pod
    finally:
        try:
            client.terminate_pod(pod.pod_id)
        except Exception:
            log.exception("Failed to terminate pod %s", pod.pod_id)
