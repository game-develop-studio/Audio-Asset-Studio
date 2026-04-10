"""레이어드 SFX 합성 — 여러 레이어를 타이밍 정렬 후 믹스다운."""
from __future__ import annotations

import logging
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)

# 레이어별 기본 볼륨 오프셋 (dB)
LAYER_DEFAULTS = {
    "impact": {"gain_db": 0, "delay_ms": 0},
    "sweetener": {"gain_db": -3, "delay_ms": 10},
    "tail": {"gain_db": -6, "delay_ms": 30},
    "whoosh": {"gain_db": -2, "delay_ms": 0},
    "ring": {"gain_db": -4, "delay_ms": 20},
}


def mix_layers(
    layer_files: dict[str, Path],
    output_path: Path,
    layer_config: dict[str, dict] | None = None,
) -> Path:
    """여러 레이어 파일을 믹스다운.

    Args:
        layer_files: {"impact": Path("impact.wav"), "sweetener": ...}
        output_path: 믹스다운 결과 경로
        layer_config: 레이어별 커스텀 설정 (gain_db, delay_ms)
    """
    config = {**LAYER_DEFAULTS, **(layer_config or {})}
    segments: list[tuple[AudioSegment, int]] = []
    max_len = 0

    for name, path in layer_files.items():
        seg = AudioSegment.from_file(str(path))
        lcfg = config.get(name, {"gain_db": 0, "delay_ms": 0})
        seg = seg.apply_gain(lcfg.get("gain_db", 0))
        delay = lcfg.get("delay_ms", 0)
        total_len = delay + len(seg)
        if total_len > max_len:
            max_len = total_len
        segments.append((seg, delay))

    if not segments:
        raise ValueError("No layers to mix")

    # 빈 캔버스에 레이어 오버레이
    mixed = AudioSegment.silent(duration=max_len, frame_rate=44100)
    for seg, delay in segments:
        mixed = mixed.overlay(seg, position=delay)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mixed.export(str(output_path), format=output_path.suffix.lstrip("."))
    log.info("Mixed %d layers → %s (%dms)", len(segments), output_path.name, max_len)
    return output_path
