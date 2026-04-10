"""페이드인/아웃."""
from __future__ import annotations

import logging
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)


def apply_fade(
    audio_path: Path,
    fade_in_ms: int = 10,
    fade_out_ms: int = 30,
    output_path: Path | None = None,
) -> Path:
    """페이드인/아웃 적용. 클릭 방지용 최소 페이드."""
    audio = AudioSegment.from_file(str(audio_path))
    fade_in_ms = min(fade_in_ms, len(audio) // 4)
    fade_out_ms = min(fade_out_ms, len(audio) // 4)
    faded = audio.fade_in(fade_in_ms).fade_out(fade_out_ms)

    out = output_path or audio_path
    faded.export(str(out), format=out.suffix.lstrip("."))
    log.info("Fade applied %s: in=%dms, out=%dms", audio_path.name, fade_in_ms, fade_out_ms)
    return out
