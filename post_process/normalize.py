"""라우드니스 정규화."""
from __future__ import annotations

import logging
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)

DEFAULT_TARGET_LUFS = -14.0


def normalize(
    audio_path: Path,
    target_dbfs: float = DEFAULT_TARGET_LUFS,
    output_path: Path | None = None,
) -> Path:
    """오디오 파일의 라우드니스를 target_dbfs로 정규화."""
    audio = AudioSegment.from_file(str(audio_path))
    change = target_dbfs - audio.dBFS
    normalized = audio.apply_gain(change)
    out = output_path or audio_path
    normalized.export(str(out), format=out.suffix.lstrip("."))
    log.info("Normalized %s: %.1f dBFS → %.1f dBFS", audio_path.name, audio.dBFS, target_dbfs)
    return out
