"""로컬 AudioCraft 추론 — MusicGen/AudioGen via transformers (MPS/CPU)."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# 모델 캐시 (같은 세션 내 재로딩 방지)
_model_cache: dict[str, tuple] = {}

MODEL_MAP = {
    "musicgen": "facebook/musicgen-small",
    "audiogen": "facebook/audiogen-medium",
}


def _get_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_model(model_name: str):
    """모델+프로세서 로드 (캐시 활용)."""
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    if model_name in _model_cache:
        return _model_cache[model_name]

    model_id = MODEL_MAP.get(model_name)
    if not model_id:
        raise ValueError(f"Unknown model: {model_name}. Expected: {list(MODEL_MAP)}")

    device = _get_device()
    log.info("Loading %s (%s) on %s ...", model_name, model_id, device)

    processor = AutoProcessor.from_pretrained(model_id)
    model = MusicgenForConditionalGeneration.from_pretrained(model_id)
    model = model.to(device)

    _model_cache[model_name] = (processor, model, device)
    log.info("Model %s ready", model_name)
    return processor, model, device


def generate_audio(
    prompt: str,
    model_name: str,
    duration_ms: int,
    seed: int,
    output_dir: Path,
    prefix: str,
) -> list[Path]:
    """로컬에서 오디오 생성 → WAV 파일 저장.

    Returns:
        생성된 WAV 파일 경로 리스트
    """
    import numpy as np
    import scipy.io.wavfile as wavfile
    import torch

    processor, model, device = _load_model(model_name)

    # 시드 고정
    torch.manual_seed(seed)
    if device == "mps":
        torch.mps.manual_seed(seed)

    # 생성 토큰 수 계산 (MusicGen: 50 tokens/sec at 32kHz)
    duration_sec = duration_ms / 1000.0
    max_new_tokens = int(duration_sec * 50)
    max_new_tokens = max(max_new_tokens, 10)

    inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)

    with torch.no_grad():
        audio_values = model.generate(**inputs, max_new_tokens=max_new_tokens)

    # (batch, channels, samples) → numpy
    audio = audio_values[0].cpu().numpy()
    if audio.ndim == 2:
        audio = audio[0]  # mono

    # float32 → int16 WAV
    audio = audio / (np.abs(audio).max() + 1e-8)
    audio_int16 = (audio * 32767).astype(np.int16)

    sample_rate = model.config.audio_encoder.sampling_rate
    out_path = output_dir / f"{prefix}.wav"
    wavfile.write(str(out_path), sample_rate, audio_int16)

    log.info("Generated %s (%.1fs, %d samples)", out_path.name, duration_sec, len(audio_int16))
    return [out_path]
