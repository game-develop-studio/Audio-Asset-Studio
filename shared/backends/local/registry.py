"""모델 이름 → 어댑터 클래스 매핑."""
from __future__ import annotations

from typing import Any

from .musicgen_adapter import MusicGenAdapter
from .audiogen_adapter import AudioGenAdapter
from .stable_audio_adapter import StableAudioAdapter


# 이름 별칭을 내부 canonical name으로 정규화
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    # MusicGen family
    "musicgen":          {"adapter": MusicGenAdapter, "variant": "facebook/musicgen-medium"},
    "musicgen-small":    {"adapter": MusicGenAdapter, "variant": "facebook/musicgen-small"},
    "musicgen-medium":   {"adapter": MusicGenAdapter, "variant": "facebook/musicgen-medium"},
    "musicgen-large":    {"adapter": MusicGenAdapter, "variant": "facebook/musicgen-large"},
    "musicgen-melody":   {"adapter": MusicGenAdapter, "variant": "facebook/musicgen-melody"},

    # AudioGen (SFX)
    "audiogen":          {"adapter": AudioGenAdapter, "variant": "facebook/audiogen-medium"},
    "audiogen-medium":   {"adapter": AudioGenAdapter, "variant": "facebook/audiogen-medium"},

    # Stable Audio Open
    "stable-audio":      {"adapter": StableAudioAdapter, "variant": "stabilityai/stable-audio-open-1.0"},
    "stable-audio-open": {"adapter": StableAudioAdapter, "variant": "stabilityai/stable-audio-open-1.0"},
}


def load_adapter(model_name: str):
    """모델 이름 → 인스턴스화된 어댑터 (로드는 lazy)."""
    key = model_name.lower()
    if key not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model '{model_name}'. Available: {sorted(MODEL_REGISTRY)}"
        )
    entry = MODEL_REGISTRY[key]
    return entry["adapter"](variant=entry["variant"])
