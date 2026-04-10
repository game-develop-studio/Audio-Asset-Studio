"""앞뒤 무음 제거."""
from __future__ import annotations

import logging
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_leading_silence

log = logging.getLogger(__name__)


def trim_silence(
    audio_path: Path,
    silence_thresh_dbfs: float = -50.0,
    output_path: Path | None = None,
) -> Path:
    """앞뒤 무음을 제거한다."""
    audio = AudioSegment.from_file(str(audio_path))
    original_len = len(audio)

    lead = detect_leading_silence(audio, silence_threshold=silence_thresh_dbfs)
    trail = detect_leading_silence(audio.reverse(), silence_threshold=silence_thresh_dbfs)

    trimmed = audio[lead:original_len - trail] if trail > 0 else audio[lead:]
    if len(trimmed) == 0:
        trimmed = audio  # 전체가 무음이면 원본 유지

    out = output_path or audio_path
    trimmed.export(str(out), format=out.suffix.lstrip("."))
    log.info("Trimmed %s: %dms → %dms", audio_path.name, original_len, len(trimmed))
    return out
