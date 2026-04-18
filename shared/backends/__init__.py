"""Generation backend 추상화.

LocalBackend (M-series MPS) / RunPodBackend / WarmPoolBackend 공통 인터페이스.
phase4는 backend 이름만 알면 됨 — 구체 구현은 어댑터가 담당.
"""
from __future__ import annotations

from .base import Backend, GenerationJob, GenerationResult, get_backend

__all__ = ["Backend", "GenerationJob", "GenerationResult", "get_backend"]
