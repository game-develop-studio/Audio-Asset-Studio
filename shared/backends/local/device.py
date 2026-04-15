"""MPS/CPU 디바이스 선택 + dtype 결정."""
from __future__ import annotations

import os


def pick_device() -> str:
    """AUDIO_DEVICE 환경변수 > MPS > CUDA > CPU."""
    forced = os.environ.get("AUDIO_DEVICE")
    if forced:
        return forced
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def torch_dtype(device: str):
    """M-series는 float32 권장 (MPS float16 불안정 케이스 존재). CUDA는 float16."""
    import torch
    if device == "cuda":
        return torch.float16
    if device == "mps":
        # MPS는 일부 op에서 fp16 문제 — 환경변수로 강제 가능
        if os.environ.get("AUDIO_MPS_FP16") == "1":
            return torch.float16
        return torch.float32
    return torch.float32


def empty_cache(device: str) -> None:
    try:
        import torch
        if device == "cuda":
            torch.cuda.empty_cache()
        elif device == "mps":
            torch.mps.empty_cache()
    except Exception:
        pass
